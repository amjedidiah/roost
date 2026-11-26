import datetime as dt
import io
import json
import os
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

import accounts
import digest
import inbox
import userspace
from due import extract_items, upcoming
from extract import ExtractError, text_from
from ingest import chunk_text
from tests.fakes import FakeBox, FakeInbox, FakeMail, FakeNest

SAMPLES = Path(__file__).resolve().parent.parent / "sample-docs"
NOW = dt.datetime(2026, 11, 26, 9, 0, tzinfo=dt.timezone.utc)
TODAY = NOW.date()


class TempData(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ROOST_DATA")
        os.environ["ROOST_DATA"] = self.tmp.name
        FakeNest.store = {}

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ROOST_DATA", None)
        else:
            os.environ["ROOST_DATA"] = self._old
        self.tmp.cleanup()


class AccountsTest(TempData):
    def test_code_signs_in_once_and_creates_user(self):
        token, code = accounts.start_signin("Ada@Example.com ", NOW)
        uid = accounts.verify_code("ada@example.com", code, NOW)
        self.assertEqual(accounts.get_user(uid)["email"], "ada@example.com")
        self.assertTrue(accounts.get_user(uid)["reminders"])
        with self.assertRaises(accounts.SignInError):
            accounts.verify_code("ada@example.com", code, NOW)  # single use
        with self.assertRaises(accounts.SignInError):
            accounts.verify_token(token, NOW)  # the link died with the code

    def test_link_signs_in_and_same_email_same_user(self):
        token, _ = accounts.start_signin("ada@example.com", NOW)
        uid = accounts.verify_token(token, NOW)
        _, code = accounts.start_signin("ada@example.com", NOW)
        self.assertEqual(accounts.verify_code("ada@example.com", code, NOW), uid)
        self.assertEqual(len(accounts.users()), 1)

    def test_expiry(self):
        token, code = accounts.start_signin("ada@example.com", NOW)
        later = NOW + dt.timedelta(minutes=16)
        with self.assertRaises(accounts.SignInError):
            accounts.verify_code("ada@example.com", code, later)
        with self.assertRaises(accounts.SignInError):
            accounts.verify_token(token, later)

    def test_wrong_codes_lock_after_five(self):
        _, code = accounts.start_signin("ada@example.com", NOW)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(4):
            with self.assertRaises(accounts.SignInError) as e:
                accounts.verify_code("ada@example.com", wrong, NOW)
            self.assertEqual(e.exception.status, 400)
        with self.assertRaises(accounts.SignInError) as e:
            accounts.verify_code("ada@example.com", wrong, NOW)
        self.assertEqual(e.exception.status, 429)
        with self.assertRaises(accounts.SignInError):
            accounts.verify_code("ada@example.com", code, NOW)  # even the right code is now refused

    def test_rate_limits(self):
        for _ in range(3):
            accounts.start_signin("ada@example.com", NOW)
        with self.assertRaises(accounts.SignInError) as e:
            accounts.start_signin("ada@example.com", NOW)
        self.assertEqual(e.exception.status, 429)
        accounts.start_signin("ada@example.com", NOW + dt.timedelta(hours=1, minutes=1))  # window passed

    def test_test_sign_ins_skip_and_never_use_the_limits(self):
        for _ in range(5):  # past the per-email limit, and none of them count
            accounts.start_signin("roost-nest@agentmail.to", NOW, test=True)
        for _ in range(3):
            accounts.start_signin("ada@example.com", NOW)
        for n in range(accounts.GLOBAL_PER_HOUR - 3):
            accounts.start_signin(f"p{n}@example.com", NOW)
        with self.assertRaises(accounts.SignInError):  # the global limit is still whole for real users...
            accounts.start_signin("late@example.com", NOW)
        _, code = accounts.start_signin("roost-nest@agentmail.to", NOW, test=True)  # ...and tests still get in
        uid = accounts.verify_code("roost-nest@agentmail.to", code, NOW)
        self.assertEqual((accounts.get_user(uid)["test"], accounts.get_user(uid)["reminders"]), (True, False))
        self.assertNotIn(uid, digest.run(lambda *a, **k: None, TODAY))  # never in the daily run

    def test_test_sign_in_works_when_full(self):
        old = accounts.MAX_USERS
        accounts.MAX_USERS = 1
        try:
            _, code = accounts.start_signin("ada@example.com", NOW)
            accounts.verify_code("ada@example.com", code, NOW)
            _, code = accounts.start_signin("roost-nest@agentmail.to", NOW, test=True)
            self.assertTrue(accounts.verify_code("roost-nest@agentmail.to", code, NOW))
        finally:
            accounts.MAX_USERS = old

    def test_user_cap(self):
        old = accounts.MAX_USERS
        accounts.MAX_USERS = 1
        try:
            _, code = accounts.start_signin("a@example.com", NOW)
            accounts.verify_code("a@example.com", code, NOW)
            with self.assertRaises(accounts.SignInError) as e:
                accounts.start_signin("b@example.com", NOW)
            self.assertEqual(e.exception.status, 403)
            accounts.start_signin("a@example.com", NOW)  # existing users can still sign in
        finally:
            accounts.MAX_USERS = old

    def test_bad_email(self):
        for bad in ("", "nope", "a@b", "a b@example.com", "x" * 250 + "@example.com"):
            with self.assertRaises(accounts.SignInError):
                accounts.start_signin(bad, NOW)

    def test_sessions(self):
        _, code = accounts.start_signin("ada@example.com", NOW)
        uid = accounts.verify_code("ada@example.com", code, NOW)
        sid = accounts.create_session(uid, NOW)
        self.assertEqual(accounts.session_user(sid, NOW), uid)
        self.assertIsNone(accounts.session_user(sid, NOW + dt.timedelta(days=31)))
        self.assertIsNone(accounts.session_user("forged", NOW))
        accounts.end_session(sid)
        self.assertIsNone(accounts.session_user(sid, NOW))
        stored = (Path(self.tmp.name) / "sessions.json").read_text() + (Path(self.tmp.name) / "signin.json").read_text()
        self.assertNotIn(sid, stored)
        self.assertNotIn(code, json.dumps([r["code"] for r in json.loads((Path(self.tmp.name) / "signin.json").read_text())]))


class DueTest(unittest.TestCase):
    def items(self, name):
        return extract_items(chunk_text((SAMPLES / name).read_text()), TODAY)

    def test_samples_give_the_expected_deadlines(self):
        files = {p.name: {"name": p.name, "due": extract_items(chunk_text(p.read_text()), TODAY)}
                 for p in SAMPLES.glob("*.md")}
        got = {(i["file"], i["due"]) for i in upcoming(files, TODAY, 400)}
        for expected in [("apartment-lease-2026.md", "2026-12-02"), ("dentist-visit-notes.md", "2026-12-04"),
                         ("car-insurance-renewal.md", "2026-12-10"), ("car-insurance-renewal.md", "2026-12-15"),
                         ("lisbon-trip-itinerary.md", "2026-12-11"), ("laptop-warranty.md", "2026-12-28"),
                         ("2026-tax-receipts.md", "2027-04-30")]:
            self.assertIn(expected, got)

    def test_wrapped_line_is_rejoined_and_todo_beats_line(self):
        lease = {i["dates"][0]: i for i in self.items("apartment-lease-2026.md")}
        item = lease["2026-12-02"]
        self.assertEqual(item["kind"], "todo")
        self.assertTrue(item["line"].startswith("Chase Calder"))

    def test_pdf_lines_stay_apart_but_wrapped_sentences_rejoin(self):
        pdf_text = ("Northgrid Energy - Electricity bill\n"
                    "Period: 20 October 2026 to 19 November 2026\n"
                    "Amount due: 84.20\n"
                    "Please pay by 12 December 2026 to avoid a late fee.\n"
                    "Payment due date\n"
                    "15 January 2027\n")
        lines = [i["line"] for i in extract_items(chunk_text(pdf_text), TODAY)]
        self.assertEqual(lines, ["Please pay by 12 December 2026 to avoid a late fee.",
                                 "Payment due date 15 January 2027"])

    def test_mixed_line_takes_the_deadline_date(self):
        lines = [i["line"] for i in self.items("2026-tax-receipts.md")]
        self.assertIn("Return due 30 April 2027", lines)
        self.assertFalse(any(l.startswith("Tax year") for l in lines))

    def test_no_deadline_word_no_item(self):
        lines = " ".join(i["line"] for i in self.items("dentist-visit-notes.md"))
        self.assertNotIn("as of 20 November", lines)
        self.assertNotIn("resets 1 January", lines)

    def test_urgency_and_overdue(self):
        files = {"f": {"name": "f.md", "due": [
            {"line": "Pay the bill by 20 November", "dates": ["2026-11-20"], "kind": "line"},
            {"line": "Call the bank before 28 November", "dates": ["2026-11-28"], "kind": "todo"},
            {"line": "Renewal due 1 March", "dates": ["2027-03-01"], "kind": "line"},
            {"line": "Old thing due 1 October", "dates": ["2026-10-01"], "kind": "line"},
        ]}}
        items = upcoming(files, TODAY, 400)
        self.assertEqual([i["due"] for i in items], ["2026-11-20", "2026-11-28", "2027-03-01"])
        self.assertTrue(items[0]["overdue"])
        self.assertEqual((items[1]["urgency"], items[1]["next_action"]), ("high", "follow_up"))
        self.assertEqual(items[2]["urgency"], "low")


def make_docx(paragraphs):
    """A minimal .docx: [(style or None, text, is_list)]."""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = ""
    for style, text, is_list in paragraphs:
        props = ""
        if style or is_list:
            props = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + \
                    ("<w:numPr><w:numId w:val=\"1\"/></w:numPr>" if is_list else "") + "</w:pPr>"
        body += f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


class ExtractTest(unittest.TestCase):
    def test_docx_headings_and_bullets_feed_the_rules(self):
        data = make_docx([("Heading1", "Bills", False), (None, "Electricity account.", False),
                          ("Heading2", "To do", False), (None, "Pay the electricity bill by 3 December", True),
                          (None, "Read the meter", True)])
        text = text_from("bills.docx", data)
        self.assertIn("## To do\n\n- Pay the electricity bill by 3 December\n- Read the meter", text)
        items = extract_items(chunk_text(text), TODAY)
        self.assertEqual([(i["kind"], i["dates"]) for i in items], [("todo", ["2026-12-03"])])

    def test_bad_files(self):
        with self.assertRaises(ExtractError):
            text_from("x.docx", b"not a zip")
        with self.assertRaises(ExtractError):
            text_from("x.exe", b"MZ")


class UserspaceTest(TempData):
    def setUp(self):
        super().setUp()
        self.box = FakeBox()
        _, code = accounts.start_signin("ada@example.com", NOW)
        self.uid = accounts.verify_code("ada@example.com", code, NOW)
        _, code = accounts.start_signin("bo@example.com", NOW)
        self.other = accounts.verify_code("bo@example.com", code, NOW)
        userspace._users_folder.clear()

    def test_samples_then_due_and_isolation(self):
        userspace.add_samples(self.uid, self.box, FakeNest)
        self.assertEqual(len(userspace.documents(self.uid)), 8)
        self.assertTrue(userspace.due(self.uid, TODAY))
        self.assertEqual(userspace.documents(self.other), [])
        self.assertEqual(userspace.due(self.other, TODAY), [])
        self.assertIn(f"u-{self.uid}", FakeNest.store)
        self.assertNotIn(f"u-{self.other}", FakeNest.store)
        users_folder = self.box.find_folder("users", self.box.roost)
        self.assertEqual(self.box.find_folder(self.uid, users_folder), accounts.get_user(self.uid)["box_folder"])

    def test_upload_limits_and_names(self):
        userspace.upload(self.uid, "../../notes.md", b"## To do\n\n- Pay rent by 1 December", self.box, FakeNest)
        self.assertEqual([d["name"] for d in userspace.documents(self.uid)], ["notes.md"])
        for bad, data in [("x.exe", b"a"), (".hidden.md", b"a"), ("e.md", b"")]:
            with self.assertRaises(userspace.LimitError):
                userspace.upload(self.uid, bad, data, self.box, FakeNest)
        with self.assertRaises(userspace.LimitError):
            userspace.upload(self.uid, "big.md", b"x" * (userspace.MAX_FILE_BYTES + 1), self.box, FakeNest)
        for n in range(9):
            userspace.upload(self.uid, f"n{n}.md", b"hello", self.box, FakeNest)
        with self.assertRaises(userspace.LimitError) as e:
            userspace.upload(self.uid, "eleventh.md", b"hello", self.box, FakeNest)
        self.assertEqual(e.exception.status, 413)
        userspace.upload(self.uid, "n0.md", b"replacing is fine", self.box, FakeNest)  # same name doesn't add

    def test_delete_empties_box_and_removes_vectors(self):
        userspace.upload(self.uid, "notes.md", b"## To do\n\n- Pay rent by 1 December", self.box, FakeNest)
        doc = userspace.documents(self.uid)[0]
        userspace.delete(self.uid, doc["id"], self.box, FakeNest)
        self.assertEqual(self.box.files[doc["id"]]["data"], b"")
        self.assertEqual(FakeNest.store[f"u-{self.uid}"], {})
        self.assertEqual(userspace.documents(self.uid), [])
        userspace.sync(self.uid, self.box, FakeNest)  # the empty file stays hidden after a sync
        self.assertEqual(userspace.documents(self.uid), [])
        with self.assertRaises(userspace.LimitError):
            userspace.delete(self.other, doc["id"], self.box, FakeNest)  # not theirs


    def test_erase_removes_everything_the_user_added(self):
        userspace.add_samples(self.uid, self.box, FakeNest)
        userspace.add_samples(self.other, self.box, FakeNest)
        sid = accounts.create_session(self.uid, NOW)
        result = userspace.erase(self.uid, self.box, FakeNest)
        self.assertEqual(result, {"email": "ada@example.com", "files_emptied": 8})
        folder_files = [f for f in self.box.files.values() if f["parent"] != accounts.get_user(self.other)["box_folder"]]
        self.assertTrue(all(f["data"] == b"" for f in folder_files))
        self.assertEqual(FakeNest.store[f"u-{self.uid}"], {})
        self.assertFalse(userspace.user_dir(self.uid).exists())
        self.assertIsNone(accounts.get_user(self.uid))
        self.assertIsNone(accounts.session_user(sid, NOW))
        self.assertEqual(len(accounts.users()), 1)  # the slot is free again
        self.assertEqual(len(userspace.documents(self.other)), 8)  # others untouched
        self.assertEqual(len(FakeNest.store[f"u-{self.other}"]) > 0, True)
        with self.assertRaises(userspace.LimitError):
            userspace.erase(self.uid, self.box, FakeNest)
        _, code = accounts.start_signin("ada@example.com", NOW)  # can sign up again, fresh
        self.assertNotEqual(accounts.verify_code("ada@example.com", code, NOW), self.uid)


class InboxTest(TempData):
    def setUp(self):
        super().setUp()
        self.box, self.mail = FakeBox(), FakeInbox()
        userspace._users_folder.clear()
        _, code = accounts.start_signin("ada@example.com", NOW)
        self.ada = accounts.verify_code("ada@example.com", code, NOW)
        _, code = accounts.start_signin("bo@example.com", NOW)
        self.bo = accounts.verify_code("bo@example.com", code, NOW)

    def test_forwarded_email_becomes_a_document_once(self):
        self.mail.add("Ada <ADA@example.com>", "Fwd: Water bill",
                      "---------- Forwarded message ---------\nAmount due: 41.00\nPlease pay by 10 December 2026.")
        result = inbox.poll(self.box, FakeNest, self.mail)
        self.assertEqual(result, {self.ada: {"added": ["Water bill.txt"], "skipped": []}})
        self.assertEqual([d["name"] for d in userspace.documents(self.ada)], ["Water bill.txt"])
        self.assertEqual(userspace.due(self.ada, TODAY)[0]["due"], "2026-12-10")
        self.assertEqual(inbox.poll(self.box, FakeNest, self.mail), {})  # not added twice
        self.assertEqual(userspace.documents(self.bo), [])

    def test_strangers_roost_itself_and_attachments(self):
        self.mail.add("stranger@example.com", "Fwd: bill", "Pay by 10 December 2026 or else, please.")
        self.mail.add("roost-nest@agentmail.to", "Your roost sign-in code: 123456", "Your code is 123456 ok")
        self.mail.add("bo@example.com", "Fwd: Gas", "", attachments=[{"filename": "gas.pdf"}])
        result = inbox.poll(self.box, FakeNest, self.mail)
        self.assertEqual(list(result), [self.bo])
        self.assertEqual(result[self.bo]["added"], [])
        self.assertIn("attachments", result[self.bo]["skipped"][0]["reason"])
        self.assertEqual(len(read_done()), 3)

    def test_html_only_email_and_only_uid(self):
        self.mail.add("bo@example.com", "FW: Hotel booking",
                      html="<p>Check-in <b>12 December 2026</b></p><p>Cancel before 5 December 2026 for a refund.</p>")
        self.mail.add("ada@example.com", "Note", "Renew the passport by 1 March 2027, please.")
        self.assertEqual(list(inbox.poll(self.box, FakeNest, self.mail, only_uid=self.ada)), [self.ada])
        self.assertEqual(len(read_done()), 1)  # Bo's email waits for Bo
        result = inbox.poll(self.box, FakeNest, self.mail)
        self.assertEqual(result[self.bo]["added"], ["Hotel booking.txt"])
        self.assertTrue(any(i["due"] == "2026-12-05" for i in userspace.due(self.bo, TODAY)))

    def test_smoke_mail_counts_only_while_fresh(self):
        _, code = accounts.start_signin("roost-nest@agentmail.to", NOW, test=True)
        tester = accounts.verify_code("roost-nest@agentmail.to", code, NOW)
        old = self.mail.add("roost-nest@agentmail.to", "roost-smoke: Fwd: Old bill", "Please pay by 10 December 2026, thanks.")
        self.mail.get(old)["timestamp"] = "2026-11-26T07:00:00Z"
        self.mail.add("roost-nest@agentmail.to", "roost-smoke: Fwd: New bill", "Please pay by 10 December 2026, thanks.")
        result = inbox.poll(self.box, FakeNest, self.mail, now=dt.datetime(2026, 11, 26, 8, 10, tzinfo=dt.timezone.utc))
        self.assertEqual(result[tester]["added"], ["New bill.txt"])

    def test_limits_apply(self):
        for n in range(userspace.MAX_FILES):
            userspace.upload(self.ada, f"n{n}.md", b"hello", self.box, FakeNest)
        self.mail.add("ada@example.com", "Fwd: one more", "Pay by 10 December 2026, thanks a lot.")
        result = inbox.poll(self.box, FakeNest, self.mail)
        self.assertEqual(result[self.ada]["added"], [])
        self.assertIn("up to", result[self.ada]["skipped"][0]["reason"])

    def test_names(self):
        self.assertEqual(inbox.document_name("Re: FWD: Fw: Council tax / 2027", "2026-11-26T08"), "Council tax 2027.txt")
        self.assertEqual(inbox.document_name("roost-smoke: Fwd: Water", ""), "Water.txt")
        self.assertEqual(inbox.document_name("", "2026-11-26T08:00"), "Forwarded email 2026-11-26.txt")


def read_done():
    from store import read_json
    return read_json(inbox._state_path(), {"done": []})["done"]


class MailBudgetTest(TempData):
    def test_users_and_tests_have_separate_budgets(self):
        import mail
        sent = []
        real, old_base = mail.gateway.request, mail.gateway.base_url
        mail.gateway.request = lambda *a, **k: sent.append(a)
        mail.gateway.base_url = lambda provider: "https://gw"
        old_budgets = dict(mail.BUDGETS)
        mail.BUDGETS.update({"user": 2, "test": 1})
        try:
            mail.send("a@example.com", "s", "t", kind="test")
            with self.assertRaises(mail.MailBudgetExceeded):
                mail.send("a@example.com", "s", "t", kind="test")
            mail.send("a@example.com", "s", "t")  # test mail didn't touch the user budget
            mail.send("a@example.com", "s", "t")
            with self.assertRaises(mail.MailBudgetExceeded):
                mail.send("a@example.com", "s", "t")
            self.assertEqual((mail.sent_today(), mail.sent_today(kind="test"), len(sent)), (2, 1, 3))
        finally:
            mail.gateway.request, mail.gateway.base_url = real, old_base
            mail.BUDGETS.clear(); mail.BUDGETS.update(old_budgets)

    def test_old_log_format_counts_as_user_mail(self):
        import mail
        from store import write_json
        write_json(mail._log_path(), {TODAY.isoformat(): 5})
        self.assertEqual((mail.sent_today(TODAY), mail.sent_today(TODAY, "test")), (5, 0))


class DigestTest(TempData):
    def setUp(self):
        super().setUp()
        self.box, self.mail = FakeBox(), FakeMail()
        _, code = accounts.start_signin("ada@example.com", NOW)
        self.uid = accounts.verify_code("ada@example.com", code, NOW)
        userspace._users_folder.clear()
        userspace.add_samples(self.uid, self.box, FakeNest)

    def test_once_a_day_with_only_the_next_week(self):
        results = digest.run(self.mail, TODAY)
        self.assertEqual(results[self.uid], "sent")
        msg = self.mail.sent[0]
        self.assertEqual(msg["to"], "ada@example.com")
        self.assertIn("Chase Calder", msg["text"])
        self.assertNotIn("Harbourline", msg["text"])  # 10 Dec is beyond 7 days
        self.assertEqual(digest.run(self.mail, TODAY)[self.uid], "already sent today")
        self.assertEqual(len(self.mail.sent), 1)

    def test_off_and_nothing_due(self):
        accounts.update_user(self.uid, reminders=False)
        self.assertEqual(digest.run(self.mail, TODAY)[self.uid], "off")
        accounts.update_user(self.uid, reminders=True)
        self.assertEqual(digest.run(self.mail, dt.date(2027, 6, 1))[self.uid], "nothing due")
        self.assertEqual(self.mail.sent, [])

    def test_html_escapes_document_text(self):
        _, _, html = digest.compose([{"line": "<script>x</script>", "file": "a&b.md", "due": "2026-11-27",
                                      "days": 1, "overdue": False}])
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


class ApiTest(TempData):
    def setUp(self):
        super().setUp()
        import service
        self.service = service
        self.box, self.mail = FakeBox(), FakeMail()
        self._seams = (service.make_box, service.make_nest, service.send_mail, service.make_inbox)
        self.inbox = FakeInbox()
        service.make_box, service.make_nest, service.send_mail = (lambda: self.box), FakeNest, self.mail
        service.make_inbox = lambda: self.inbox
        userspace._users_folder.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.cookie = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        (self.service.make_box, self.service.make_nest, self.service.send_mail,
         self.service.make_inbox) = self._seams
        super().tearDown()

    def call(self, method, path, body=None, headers=None, csrf=True, raw=None):
        h = dict(headers or {})
        if csrf and method == "POST":
            h["X-Requested-With"] = "roost"
        if self.cookie:
            h["Cookie"] = self.cookie
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                status, resp_headers, payload = r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            status, resp_headers, payload = e.code, e.headers, e.read()
        cookie = resp_headers.get("Set-Cookie")
        if cookie:
            self.cookie = cookie.split(";")[0]
        return status, resp_headers, (json.loads(payload) if payload else None)

    def sign_in(self, email="ada@example.com"):
        self.assertEqual(self.call("POST", "/api/auth/start", {"email": email})[0], 200)
        code = re.search(r"code is (\d{6})", self.mail.sent[-1]["text"]).group(1)
        status, headers, _ = self.call("POST", "/api/auth/verify", {"email": email, "code": code})
        self.assertEqual(status, 200)
        return headers

    def test_full_flow(self):
        self.assertEqual(self.call("GET", "/api/me")[2], {"signed_in": False, "full": False})
        self.assertEqual(self.call("GET", "/api/due")[0], 401)
        headers = self.sign_in()
        set_cookie = headers["Set-Cookie"]
        for flag in ("HttpOnly", "Secure", "SameSite=Lax"):
            self.assertIn(flag, set_cookie)
        me = self.call("GET", "/api/me")[2]
        self.assertEqual((me["signed_in"], me["email"]), (True, "ada@example.com"))

        self.assertEqual(self.call("POST", "/api/samples")[0], 200)
        items = self.call("GET", "/api/due?days=30")[2]["items"]
        self.assertEqual(items[0]["file"], "apartment-lease-2026.md")

        status, _, body = self.call("POST", "/api/upload", raw=b"## To do\n\n- Pay rent by 1 December",
                                    headers={"X-Filename": "rent%20notes.md"})
        self.assertEqual(status, 200)
        self.assertIn("rent notes.md", [d["name"] for d in body["documents"]])
        self.assertEqual(self.call("POST", "/api/upload", raw=b"x", headers={"X-Filename": "a.exe"})[0], 415)

        doc = next(d for d in body["documents"] if d["name"] == "rent notes.md")
        self.assertEqual(self.call("POST", f"/api/documents/{doc['id']}/delete")[0], 200)
        self.assertEqual(self.call("POST", "/api/settings", {"reminders": False})[2], {"reminders": False})
        status, _, body = self.call("POST", "/api/digest/test")
        self.assertEqual(body["result"], "sent")

        self.assertEqual(self.call("POST", "/api/auth/signout")[0], 200)
        self.assertEqual(self.call("GET", "/api/due")[0], 401)

    def test_check_for_changes_reads_forwarded_email(self):
        self.sign_in()
        self.inbox.add("ada@example.com", "Fwd: Phone bill", "Please pay by 10 December 2026 to keep the line.")
        status, _, body = self.call("POST", "/api/sync")
        self.assertEqual((status, body["forwarded"]["added"]), (200, ["Phone bill.txt"]))
        self.assertEqual([d["name"] for d in body["documents"]], ["Phone bill.txt"])

    def test_csrf_header_required(self):
        self.sign_in()
        self.assertEqual(self.call("POST", "/api/samples", csrf=False)[0], 403)

    def test_users_cannot_see_each_other(self):
        self.sign_in("ada@example.com")
        self.call("POST", "/api/samples")
        ada_docs = self.call("GET", "/api/documents")[2]["documents"]
        self.cookie = None
        self.sign_in("bo@example.com")
        self.assertEqual(self.call("GET", "/api/documents")[2]["documents"], [])
        self.assertEqual(self.call("POST", f"/api/documents/{ada_docs[0]['id']}/delete")[0], 404)

    def test_link_sign_in_sets_cookie_and_redirects(self):
        self.call("POST", "/api/auth/start", {"email": "ada@example.com"})
        token = re.search(r"/auth\?t=(\S+)", self.mail.sent[-1]["text"]).group(1)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(self.base + "/auth?t=" + token)
        except urllib.error.HTTPError as e:
            self.assertEqual((e.code, e.headers["Location"]), (303, "/"))
            self.assertIn("roost_session=", e.headers["Set-Cookie"])
        try:
            opener.open(self.base + "/auth?t=" + token)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.headers["Location"], "/?signin=expired")

    def test_internal_routes_need_owner_token(self):
        self.assertIn(self.call("POST", "/internal/digest")[0], (401, 503))
        self.assertIn(self.call("POST", "/internal/delete-user", {"all": True})[0], (401, 503))

    def test_owner_token_marks_a_test_sign_in(self):
        from auth import token_hash
        (Path(self.tmp.name) / "token.sha256").write_text(token_hash("t0ken") + "\n")
        status, _, body = self.call("POST", "/api/auth/start", {"email": "roost-nest@agentmail.to"},
                                    {"X-Roost-Token": "wrong"})
        self.assertEqual((status, self.mail.sent), (403, []))  # a bad token is refused, not downgraded
        for _ in range(4):  # past the per-email limit
            self.assertEqual(self.call("POST", "/api/auth/start", {"email": "roost-nest@agentmail.to"},
                                       {"X-Roost-Token": "t0ken"})[0], 200)
        self.assertEqual({m["kind"] for m in self.mail.sent}, {"test"})
        self.sign_in()  # a real user is unaffected and uses the user budget
        self.assertEqual(self.mail.sent[-1]["kind"], "user")

    def test_account_delete_signs_out_and_frees_the_slot(self):
        self.sign_in()
        self.assertEqual(self.call("POST", "/api/samples")[0], 200)
        self.assertEqual(self.call("POST", "/api/account/delete", csrf=False)[0], 403)
        status, headers, body = self.call("POST", "/api/account/delete")
        self.assertEqual((status, body["deleted"], body["files_emptied"]), (200, True, 8))
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(accounts.users(), {})
        self.assertEqual(self.call("GET", "/api/documents")[0], 401)

    def test_owner_can_delete_one_user_or_everyone(self):
        from auth import token_hash
        (Path(self.tmp.name) / "token.sha256").write_text(token_hash("t0ken") + "\n")
        owner = {"X-Roost-Token": "t0ken"}
        self.sign_in("ada@example.com")
        self.cookie = None
        self.sign_in("bo@example.com")
        status, _, body = self.call("POST", "/internal/delete-user", {"email": "Ada@Example.com"}, owner)
        self.assertEqual((status, [d["email"] for d in body["deleted"]]), (200, ["ada@example.com"]))
        self.assertEqual(self.call("POST", "/internal/delete-user", {"email": "ada@example.com"}, owner)[0], 404)
        status, _, body = self.call("POST", "/internal/delete-user", {"all": True}, owner)
        self.assertEqual((status, [d["email"] for d in body["deleted"]]), (200, ["bo@example.com"]))
        self.assertEqual(accounts.users(), {})


if __name__ == "__main__":
    unittest.main()
