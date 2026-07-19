import google.generativeai as genai
from .config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

async def generate_rich_html(news_text: str) -> str:
    prompt = f"""
    Ты — профессиональный редактор новостного Telegram-канала.
    Перепиши следующий текст новости в красивый, структурированный HTML-код,
    который можно отправить через Telegram (поддерживается <b>, <i>, <a>, <code>, <pre>, <blockquote>, таблицы, списки).
    Используй эмодзи для оживления. Сделай заголовок ярким.
    Верни только HTML-код без лишних комментариев и без обрамления ```html.
    
    Текст новости:
    {news_text}
    """
    response = await model.generate_content_async(prompt)
    return response.text.strip()