import pytest

import crawler

from tranco import Tranco


class TestSitelist:

    @pytest.mark.parametrize("num_sites, exclude_suffixes, exclude_domains, expected", [
        ("10", None, set(), ["example.com", "example.net", "example.org", "google.com"]),
        ("1", None, set(), ["example.com"]),
        ("10", ".com", set(), ["example.net", "example.org"]),
        ("10", ".gov,.mil,.net,.org", set(), ["example.com", "google.com"]),
        ("1", ".gov", set(), ["example.com"]),
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

        # mock out Tranco list
        class MockResponse:
            def top(self):
                return ["example.com", "example.net", "example.org",
                        "google.co.uk", "google.com"]

        def mock_get(self, list_version): # pylint:disable=unused-argument
            return MockResponse()

        monkeypatch.setattr(Tranco, "list", mock_get)

        # also mock out exclude_domains
        monkeypatch.setattr(cr, "exclude_domains", exclude_domains)

        assert cr.get_domain_list() == expected

    @pytest.mark.skip()
    def test_recently_failed_domains(self):
        pass
