import os
import asyncio
import sqlite3
import pandas as pd
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
import uvicorn
import threading

API_TOKEN = os.getenv("API_TOKEN")
DB_NAME = 'shifts.db'

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

app = FastAPI()

keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(KeyboardButton("🔔 Вышел на смену"))
keyboard.add(KeyboardButton("🔕 Завершил смену"))

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            full_name TEXT,
            start_time TEXT,
            end_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.full_name}!\nНажми кнопку, чтобы начать или завершить смену.",
        reply_markup=keyboard
    )

@dp.message_handler(lambda m: m.text == "🔔 Вышел на смену")
async def start_shift(message: types.Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM shifts WHERE user_id = ? AND end_time IS NULL", (user_id,))
    if c.fetchone():
        await message.answer("❗ У тебя уже есть активная смена.")
    else:
        c.execute("INSERT INTO shifts (user_id, full_name, start_time) VALUES (?, ?, ?)",
                  (user_id, full_name, now))
        conn.commit()
        await message.answer(f"✅ Смена начата в {datetime.now().strftime('%H:%M:%S')}.")
    conn.close()

@dp.message_handler(lambda m: m.text == "🔕 Завершил смену")
async def end_shift(message: types.Message):
    user_id = message.from_user.id
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, start_time FROM shifts WHERE user_id = ? AND end_time IS NULL", (user_id,))
    row = c.fetchone()
    if row:
        shift_id, start_time = row
        c.execute("UPDATE shifts SET end_time = ? WHERE id = ?", (now, shift_id))
        conn.commit()
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(now)
        duration = end_dt - start_dt
        hours = round(duration.total_seconds() / 3600, 2)
        await message.answer(f"🔚 Смена завершена. Отработано: {hours} ч.")
    else:
        await message.answer("❗ Активная смена не найдена.")
    conn.close()

@app.get("/report")
def get_report():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM shifts", conn)
    df['start_time'] = pd.to_datetime(df['start_time'])
    df['end_time'] = pd.to_datetime(df['end_time'])
    df['worked_hours'] = (df['end_time'] - df['start_time']).dt.total_seconds() / 3600
    df.to_excel("shifts_report.xlsx", index=False)
    conn.close()
    return FileResponse("shifts_report.xlsx", media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename="shifts_report.xlsx")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    json_data = await request.json()
    update = types.Update(**json_data)
    await dp.process_update(update)
    return {"status": "ok"}

def start_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=start_fastapi, daemon=True).start()
    executor.start_polling(dp, skip_updates=True)
