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
        args = ["firefox", "10"]
        args.append("--exclude=" + exclude_suffixes)

        cr = crawler.Crawler(crawler.create_argument_parser().parse_args(args))

        monkeypatch.setattr(Tranco, "list", self.mock_tranco_list)
        monkeypatch.setattr(cr, "exclude_domains", set())

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
        args = ["firefox", num_sites]
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
                return "abcde\nfghij"

            if cmd == "git show abcde:log.txt":
                return "\n".join(["WebDriverException on example.com: XXX",
                    "Timed out loading example.biz",
                    "Timed out loading example.co.uk",
                    "Timed out loading extension page",])

            if cmd == "git show fghij:log.txt":
                return "\n".join(["WebDriverException on example.org: YYY",
                    "Timed out loading extension page",
                    "Timed out loading example.co.uk",
                    "InsecureCertificateException on example.net: ZZZ"])

            return ""

        monkeypatch.setattr(crawler, "run", mock_run)

        assert crawler.get_recently_failed_domains() == set(["example.com",
                                                             "example.net",
                                                             "example.org",
                                                             "example.co.uk"])
