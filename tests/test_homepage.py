import importlib.util
import io
import json
import pathlib
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "boss_cdp_raw.py"


def load_module():
    sys.modules.setdefault("websocket", mock.Mock())
    sys.modules.setdefault("requests", mock.Mock())
    spec = importlib.util.spec_from_file_location("boss_cdp_raw_homepage", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def job(name, job_id):
    return {
        "jobName": name,
        "encryptJobId": job_id,
        "salaryDesc": "20-40K·13薪",
        "brandName": "示例公司",
        "cityName": "上海",
        "areaDistrict": "浦东新区",
        "jobExperience": "经验不限",
        "jobDegree": "本科",
        "jobLabels": ["AI", "Python"],
        "welfareList": ["五险一金"],
    }


class FakeCDP:
    def __init__(self, events, bodies):
        self.events = list(events)
        self.bodies = bodies
        self.body_requests = []

    def recv_event(self, timeout=1.0, sid=None):
        if not self.events:
            return None
        return self.events.pop(0)

    def send(self, method, params=None, sid=None, timeout=30):
        if method != "Network.getResponseBody":
            raise AssertionError(f"unexpected CDP method: {method}")
        request_id = params["requestId"]
        self.body_requests.append(request_id)
        return {"result": {"body": json.dumps(self.bodies[request_id], ensure_ascii=False)}}


class HomepageTests(unittest.TestCase):
    def test_cdp_send_preserves_events_for_homepage_capture(self):
        module = load_module()

        class FakeWebSocket:
            def __init__(self):
                self.messages = [
                    json.dumps({
                        "method": "Network.responseReceived",
                        "sessionId": "session",
                        "params": {},
                    }),
                    json.dumps({"id": 1, "result": {}}),
                ]
                self.timeout = 60

            def send(self, value):
                self.sent = value

            def recv(self):
                return self.messages.pop(0)

            def gettimeout(self):
                return self.timeout

            def settimeout(self, value):
                self.timeout = value

            def close(self):
                pass

        websocket = FakeWebSocket()
        module.require_runtime_dependencies = lambda *names: True
        module.requests = mock.Mock()
        module.requests.get.return_value.json.return_value = {
            "webSocketDebuggerUrl": "ws://test",
        }
        module.websocket = mock.Mock()
        module.websocket.create_connection.return_value = websocket
        module.websocket.WebSocketTimeoutException = TimeoutError

        session = module.CDPSession()
        self.assertEqual(session.send("Page.enable", sid="session"), {"id": 1, "result": {}})
        self.assertEqual(session.recv_event(sid="session")["method"], "Network.responseReceived")

    def test_nested_payload_extracts_public_job_and_safe_source(self):
        module = load_module()
        data = {
            "code": 0,
            "zpData": {"data": {"jobList": [job("精选 Agent", "job-selected")] }},
        }
        jobs, sources = module.normalize_homepage_payload(
            data,
            "https://www.zhipin.com/wapi/recommend/job/list.json?sortType=1&securityId=secret",
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "精选 Agent")
        self.assertEqual(jobs[0]["homepage_section"], "selected")
        self.assertEqual(jobs[0]["security_id"], "")
        self.assertEqual(jobs[0]["lid"], "")
        self.assertNotIn("secret", json.dumps(jobs + sources, ensure_ascii=False))
        self.assertEqual(sources[0]["response_path"], "/wapi/recommend/job/list.json")

    def test_sort_type_classifies_selected_and_latest(self):
        module = load_module()
        self.assertEqual(
            module.classify_homepage_section(
                "https://www.zhipin.com/wapi/home?sortType=1", "$.selected"
            ),
            "selected",
        )
        self.assertEqual(
            module.classify_homepage_section(
                "https://www.zhipin.com/wapi/home?sortType=2", "$.latest"
            ),
            "latest",
        )

    def test_business_error_is_not_treated_as_empty_success(self):
        module = load_module()
        with self.assertRaises(module.BossAPIError) as context:
            module.normalize_homepage_payload({"code": 37, "message": "环境存在异常"})
        self.assertEqual(context.exception.code, 37)

    def test_capture_stops_after_selected_and_latest_responses(self):
        module = load_module()
        selected_url = "https://www.zhipin.com/wapi/home?sortType=1"
        latest_url = "https://www.zhipin.com/wapi/home?sortType=2"
        events = [
            {"method": "Network.responseReceived", "params": {
                "requestId": "selected", "response": {
                    "url": selected_url, "mimeType": "application/json"
                },
            }},
            {"method": "Network.loadingFinished", "params": {"requestId": "selected"}},
            {"method": "Network.responseReceived", "params": {
                "requestId": "latest", "response": {
                    "url": latest_url, "mimeType": "application/json"
                },
            }},
            {"method": "Network.loadingFinished", "params": {"requestId": "latest"}},
            {"method": "Network.responseReceived", "params": {
                "requestId": "unseen", "response": {
                    "url": "https://www.zhipin.com/wapi/ignored", "mimeType": "application/json"
                },
            }},
        ]
        cdp = FakeCDP(
            events,
            {
                "selected": {"code": 0, "zpData": {"jobList": [job("精选 Agent", "job-1")]}},
                "latest": {"code": 0, "zpData": {"jobList": [job("最新 Python", "job-2")]}},
            },
        )

        jobs, sources = module.wait_for_homepage_job_responses(cdp, "session", timeout=1)

        self.assertEqual({item["title"] for item in jobs}, {"精选 Agent", "最新 Python"})
        self.assertEqual({item["section"] for item in sources}, {"selected", "latest"})
        self.assertEqual(cdp.body_requests, ["selected", "latest"])
        self.assertEqual(len(cdp.events), 1)

    def test_homepage_url_must_be_https_zhipin(self):
        module = load_module()
        with self.assertRaises(ValueError):
            module.scrape_homepage("https://example.com/", output_path="-")

    def test_scrape_result_does_not_retain_homepage_query_or_response_url(self):
        module = load_module()
        cdp = mock.Mock()
        module.CDPSession = mock.Mock(return_value=cdp)
        module.create_page_session = mock.Mock(return_value=("target", "session"))
        module.incr_request = mock.Mock()
        module.wait_for_homepage_job_responses = mock.Mock(return_value=(
            [{
                "title": "精选 Agent",
                "salary": "20-40K",
                "encrypt_job_id": "job-1",
                "job_link": "https://www.zhipin.com/job_detail/job-1.html",
                "homepage_section": "selected",
                "homepage_source_path": "$.zpData.jobList",
                "homepage_response_path": "/wapi/home",
            }],
            [{
                "section": "selected",
                "json_path": "$.zpData.jobList",
                "response_path": "/wapi/home",
                "job_count": 1,
            }],
        ))

        with redirect_stdout(io.StringIO()):
            result = module.scrape_homepage(
                "https://www.zhipin.com/chengdu/?token=secret",
                output_path="-",
                capture_seconds=1,
            )

        self.assertEqual(result["homepage_path"], "/chengdu/")
        self.assertNotIn("token=secret", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("homepage_response_url", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
