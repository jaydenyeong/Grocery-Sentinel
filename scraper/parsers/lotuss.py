from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from scraper.parsers.base import StoreParser, register


class LotussParser(StoreParser):
    slug = "lotuss"
    display_name = "Lotus's"
    domains = ["lotuss.com.my", "www.lotuss.com.my"]

    def parse_price(self, html: str) -> Decimal | None:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("h6", class_="MuiTypography-subtitle1")
        if title is None:
            return None
        for candidate in title.find_all_next("p", class_="MuiTypography-body1"):
            raw = candidate.get_text(strip=True)
            text = raw.replace("RM", "").replace(",", "").strip()
            try:
                return Decimal(text)
            except InvalidOperation:
                continue
        return None


register(LotussParser())
