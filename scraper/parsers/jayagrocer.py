from decimal import Decimal

from bs4 import BeautifulSoup

from scraper.parsers.base import StoreParser, register


class JayaGrocerParser(StoreParser):
    slug = "jayagrocer"
    display_name = "JayaGrocer"
    domains = ["jayagrocer.com", "www.jayagrocer.com"]

    def parse_price(self, html: str) -> Decimal | None:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        if h1 is None:
            return None
        price_el = h1.find_next("span", class_="price")
        if price_el is None:
            return None
        raw = price_el.get_text(strip=True)
        text = raw.replace("RM", "").replace(",", "").strip()
        return Decimal(text)


register(JayaGrocerParser())
