import pytest

import crawler

from tranco import Tranco


class TestSitelist:

    @pytest.mark.parametrize("num_sites, exclude, expected", [
        ("10", None, ["example.com", "example.net", "example.org"]),
        ("1", None, ["example.com"]),
        ("10", ".com", ["example.net", "example.org"]),
        ("10", ".gov,.mil,.net,.org", ["example.com"]),
        ("1", ".gov", ["example.com"])])
    def test_exclude_suffixes(self, monkeypatch, num_sites, exclude, expected):
        args = ["firefox", num_sites]
        if exclude:
            args.append("--exclude=" + exclude)
        cr = crawler.Crawler(crawler.create_argument_parser().parse_args(args))

        # mock out Tranco list
        class MockResponse:
            def top(self):
                return ["example.com", "example.net", "example.org"]

        def mock_get(self, list_version): # pylint:disable=unused-argument
            return MockResponse()

        monkeypatch.setattr(Tranco, "list", mock_get)

        # also clear exclude_domains
        monkeypatch.setattr(cr, "exclude_domains", set())

        assert cr.get_domain_list() == expected

    @pytest.mark.skip()
    def test_recently_failed_domains(self):
        pass
