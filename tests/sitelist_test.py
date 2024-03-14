import pytest

import crawler

from tranco import Tranco


class TestSitelist:

    def mock_tranco_list(self, list_version): # pylint:disable=unused-argument
        class MockResponse:
            def top(self):
                return ["example.com", "example.net", "example.org",
                        "google.co.uk", "google.com"]
        return MockResponse()

    @pytest.mark.parametrize("exclude_suffixes, expected", [
        (".com", ["example.net", "example.org"]),
        (".net,.org", ["example.com", "google.com"]),
        (".?om,.or?", ["example.net"]),
        (".net,.org,google", ["example.com", "google.com"])])
    def test_excluding_suffixes(self, monkeypatch, exclude_suffixes, expected):
        args = ["firefox", "10", "--exclude-failures-since=off"]
        args.append("--exclude=" + exclude_suffixes)

        cr = crawler.Crawler(crawler.create_argument_parser().parse_args(args))

        monkeypatch.setattr(Tranco, "list", self.mock_tranco_list)

        assert cr.get_domain_list() == expected

    @pytest.mark.parametrize("num_sites, exclude_suffixes, exclude_domains, expected", [
        ("10", None, set(), ["example.com", "example.net", "example.org", "google.com"]),
        ("1", None, set(), ["example.com"]),
        ("10", None, set(["example.net"]), ["example.com", "example.org", "google.com"]),
        ("10", ".com", set(["example.net"]), ["example.org"]),
        ("1", ".org", set(["example.com"]), ["example.net"])])
    def test_get_domain_list(self, # pylint:disable=too-many-arguments
                             monkeypatch,
                             num_sites, exclude_suffixes, exclude_domains, expected):
        args = ["firefox", num_sites, "--exclude-failures-since=off"]
        if exclude_suffixes:
            args.append("--exclude=" + exclude_suffixes)

        cr = crawler.Crawler(crawler.create_argument_parser().parse_args(args))

        monkeypatch.setattr(Tranco, "list", self.mock_tranco_list)
        monkeypatch.setattr(cr, "exclude_domains", exclude_domains)

        assert cr.get_domain_list() == expected

    def test_get_recently_failed_domains(self, monkeypatch):
        def mock_run(cmd, cwd=None): # pylint:disable=unused-argument
            cmd = " ".join(cmd)

            if cmd == "git rev-list --since='1 week ago' HEAD -- log.txt":
                return "abcde\nfghij\nklmno"

            if cmd == "git show abcde:log.txt":
                return "\n".join(["Visiting 1: example.com",
                    "WebDriverException on example.com: XXX",
                    "Visiting 2: example.biz",
                    "Timed out loading example.biz",
                    "Visiting 3: example.co.uk",
                    "Timed out loading example.co.uk",
                    "Timed out loading extension page",
                    "Timed out loading extension page"])

            if cmd == "git show fghij:log.txt":
                return "\n".join(["Visiting 1: example.org",
                    "WebDriverException on example.org: YYY",
                    "Timed out loading extension page",
                    "Visiting 2: example.co.uk",
                    "Timed out loading example.co.uk",
                    "Visiting 3: example.biz",
                    "Visiting 4: example.website",
                    "Timed out loading example.website",
                    "Visiting 5: example.net",
                    "InsecureCertificateException on example.net: ZZZ"])

            if cmd == "git show klmno:log.txt":
                return "\n".join(["Visiting 1: example.website",
                    "Timed out loading example.website",
                    "Visiting 2: example.com",
                    "Error loading extension page (JavascriptException):",
                    "Visiting 3: example.us",
                    "Error loading example.us:"])

            return ""

        monkeypatch.setattr(crawler, "run", mock_run)

        expected_domains_set = set(["example.com", "example.net",
                                    "example.org", "example.co.uk",
                                    "example.website", "example.us"])

        assert crawler.get_recently_failed_domains("1 week ago") == expected_domains_set
