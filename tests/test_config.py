import dataclasses

import pytest

from config import ScraperConfig, get_config


class TestDefaults:
    def test_defaults_match_the_original_hardcoded_behavior(self):
        config = get_config()

        assert config.keyword == "Working Student Software Engineer"
        assert config.location == "Berlin"
        assert config.max_jobs == 5
        assert config.login_wait_seconds == 60
        assert config.start_maximized is True

    def test_get_config_returns_a_scraper_config(self):
        assert isinstance(get_config(), ScraperConfig)

    def test_get_config_returns_equal_configs_on_every_call(self):
        assert get_config() == get_config()


class TestOverrides:
    def test_individual_values_can_be_overridden_at_construction(self):
        config = ScraperConfig(keyword="Data Engineer", max_jobs=10)

        assert config.keyword == "Data Engineer"
        assert config.max_jobs == 10

    def test_unspecified_values_keep_their_defaults(self):
        config = ScraperConfig(keyword="Data Engineer")

        assert config.location == "Berlin"
        assert config.login_wait_seconds == 60


class TestImmutability:
    @pytest.mark.parametrize(
        "field, value",
        [
            ("keyword", "other"),
            ("location", "Munich"),
            ("max_jobs", 99),
            ("login_wait_seconds", 1),
            ("start_maximized", False),
        ],
    )
    def test_fields_cannot_be_reassigned(self, field, value):
        config = get_config()

        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(config, field, value)
