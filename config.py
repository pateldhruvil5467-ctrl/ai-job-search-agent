from dataclasses import dataclass


@dataclass(frozen=True)
class ScraperConfig:
    """Runtime configuration for a single scraping run.

    Defaults match the values previously hardcoded in main.py.
    """

    keyword: str = "Working Student Software Engineer"
    location: str = "Berlin"
    max_jobs: int = 5
    login_wait_seconds: int = 60
    start_maximized: bool = True


def get_config() -> ScraperConfig:
    """Return the active scraper configuration.

    Single seam for later env-var/CLI-argument support without changing callers.
    """
    return ScraperConfig()
