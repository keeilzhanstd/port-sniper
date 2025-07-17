import time
import logging
import requests
import os
from typing import List, Dict
from portalsmp.portalsapi import search
from dotenv import load_dotenv

# === Загрузка конфигурации из .env ===
load_dotenv()

AUTH_DATA = os.getenv("AUTH_DATA") 
BOT_TOKEN = os.getenv("BOT_TOKEN") # moi bot kotoryi kidaet alery v ls @GiftWakeAlertBot
CHAT_ID = os.getenv("CHAT_ID") # mojesh naiti svoi id cherez  @userinfobot
WANTED_PROFIT_PERCENT = -5  # теперь используем -5%
PRICE_LIMIT = 10.0
WANTED_FLOOR_PROFIT = -5  # теперь используем -5%
RARITY_THRESHOLD = 0.5
TARGET_GIFT_NAME = "Jester Hat"  # Название коллекции для мониторинга
FAIR_VALUE_PROFIT = -20  # Новый фильтр по справедливой цене

class GiftAnalyzer:
    def __init__(self):
        self.processed = {}  # gift_id: price
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def alert(self, gift: Dict, profit: float, floor_profit: float, fair_value: float, fair_value_profit: float, log_msg):
        url = gift.get('photo_url', '')
        slug = url.split('/')[-1].split('.')[0]  # 'cookieheart-116518'
        model = 'NA'
        rarity = 'NA'
        for attr in gift.get('attributes', []):
                if attr.get('type', '').lower() == 'model':
                    model = attr.get('value', '')
                    rarity = attr.get('rarity_per_mille', '')
        msg = f"""🆕 Новый подарок:
        https://t.me/nft/{slug}
        {log_msg}
        {gift['name']} Model: {model} ({rarity}%)
    Price: {gift['price']} TON
    Fair Price: {fair_value} TON
    Profit: {profit:.2f}%
    Floor profit: {floor_profit:.2f}%
    Fair Value profit: {fair_value_profit:.2f}%
"""
    
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": CHAT_ID,
                    "text": msg,
                    "reply_markup": {
                        "inline_keyboard": [[
                            {
                                "text": "Открыть в Portals",
                                "url": f"https://t.me/portals/market?startapp=gift_{gift['id']}"
                            }
                        ]]
                    }
                }
            )
        except Exception as e:
            logging.error(f"❌ Ошибка отправки Telegram: {e}")

    @staticmethod
    def calculate_profit(current_price: float, reference_price: float) -> float:
        if current_price == 0:
            return 0.0
        return ((reference_price - current_price) / current_price) * 100

    def analyze(self, gift: Dict, history: List[Dict]) -> bool:
        gift_id = gift.get("id")
        if not gift_id:
            return False

        try:
            price = float(gift['price'])
            if gift_id in self.processed and self.processed[gift_id] == price:
                return False

            rarity = None
            for attr in gift.get('attributes', []):
                if attr.get('type', '').lower() == 'model':
                    value = attr.get('rarity_per_mille', '')
                    try:
                        rarity = float(value)
                    except ValueError:
                        rarity = None
                    break

            if rarity is None or rarity > RARITY_THRESHOLD:
                return False

            if not isinstance(history, list) or len(history) < 2:
                return False

            avg_price = float(history[1]['price']) # НАДО ПОМЕНЯТЬ НА АВЕРАГУ ПО КОНКРЕТНОЙ МОДЕЛИ которую рассматриваем.
            floor_price = min(float(g['price']) for g in history if 'price' in g)

            # Новый расчёт: средняя цена предыдущих продаж конкретного подарка (fair value) UPD: НАДО СМОТРЕТЬ marketActivity последние 5 продаж по какой цене? и среднюю цену.
            past_sales = [g for g in history if g.get('id') != gift_id and g.get('name') == gift.get('name')]
            

            # TODO Доделать логику вычисления Fair Price для редких
            fair_prices = [float(g['price']) for g in past_sales if 'price' in g]
            fair_value = sum(fair_prices) / len(fair_prices) if fair_prices else avg_price
            fair_value_profit = self.calculate_profit(price, fair_value)

            profit = self.calculate_profit(price, avg_price)
            floor_profit = self.calculate_profit(price, floor_price)

            model = 'NA'
            rarity = 'NA'
            for attr in gift.get('attributes', []):
                if attr.get('type', '').lower() == 'model':
                    model = attr.get('value', '')
                    rarity = attr.get('rarity_per_mille', '')

            log_msg = f"🎁 {TARGET_GIFT_NAME} {model} ({rarity}%) | Цена: {price:.2f} | Средняя: {avg_price:.2f} | Fair: {fair_value:.2f} | Profit: {profit:.2f}% | Floor: {floor_price:.2f} | Floor profit: {floor_profit:.2f}% | Fair value profit: {fair_value_profit:.2f}%"
            logging.info(f"🎁 {TARGET_GIFT_NAME} {model} ({rarity}%) | Цена: {price:.2f} | Средняя: {avg_price:.2f} | Fair: {fair_value:.2f} | Profit: {profit:.2f}% | Floor: {floor_price:.2f} | Floor profit: {floor_profit:.2f}% | Fair value profit: {fair_value_profit:.2f}%")

            if (#profit >= WANTED_PROFIT_PERCENT and
                price <= PRICE_LIMIT and
                #floor_profit >= WANTED_FLOOR_PROFIT and
                fair_value_profit >= FAIR_VALUE_PROFIT):
                self.alert(gift, profit, floor_profit, fair_value, fair_value_profit, log_msg)
                self.processed[gift_id] = price
                return True

        except Exception as e:
            logging.error(f"❌ Ошибка анализа подарка {gift_id}: {e}")

        return False

    def run(self):
        while True:
            try:
                try:
                    history = search(sort="price_asc", gift_name=TARGET_GIFT_NAME, limit=100, authData=AUTH_DATA)                  
                except Exception as e:
                    if "429" in str(e):
                        logging.warning("🔁 Слишком много запросов, пауза 60 сек")
                        time.sleep(60)
                        continue
                    else:
                        raise

                if not isinstance(history, list):
                    logging.warning(f"⚠️ search вернул не список для {TARGET_GIFT_NAME}: {history}")
                    time.sleep(60)
                    continue

                for gift in history:
                    self.analyze(gift, history)
                time.sleep(20)
            except Exception as e:
                logging.error(f"❌ Основной цикл: {e}")
                time.sleep(120)

if __name__ == '__main__':
    GiftAnalyzer().run()
