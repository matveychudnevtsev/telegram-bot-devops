import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import psycopg2
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния разговора
CHOOSING, TYPING_HABIT, TYPING_REMINDER, TYPING_HABIT_DONE = range(4)

# Подключение к базе данных
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_keyboard = [['Добавить привычку', 'Установить напоминание'],
                      ['Отметить выполнение', 'Статистика'],
                      ['Список привычек и напоминаний']]
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSING

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}")
    if update.effective_message:
        await update.effective_message.reply_text("Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз.")


# Создание таблиц в базе данных
def create_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS habits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            habit_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            reminder_text TEXT NOT NULL,
            reminder_time TIMESTAMP NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS habit_logs (
            id SERIAL PRIMARY KEY,
            habit_id INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (habit_id) REFERENCES habits (id)
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Привет! Я бот для отслеживания привычек и напоминаний."
    )
    return await menu(update, context)

# Обработчик добавления привычки
async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Какую привычку вы хотите добавить? (Или используйте /menu для возврата в главное меню)"
    )
    return TYPING_HABIT

# Сохранение новой привычки
async def save_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    habit_name = update.message.text
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO habits (user_id, habit_name) VALUES (%s, %s)", (user_id, habit_name))
        conn.commit()
        await update.message.reply_text(f"Привычка '{habit_name}' добавлена!")
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text("Произошла ошибка при сохранении привычки. Пожалуйста, попробуйте еще раз.")
    finally:
        cur.close()
        conn.close()

    return await menu(update, context)

# Обработчик установки напоминания
async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "О чем вам напомнить? (Например: 'Выпить воду через 30 минут') "
        "(Или используйте /menu для возврата в главное меню)"
    )
    return TYPING_REMINDER

# Сохранение нового напоминания
async def save_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    reminder_text = update.message.text
    reminder_time = datetime.now() + timedelta(minutes=30)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO reminders (user_id, reminder_text, reminder_time) VALUES (%s, %s, %s)",
                    (user_id, reminder_text, reminder_time))
        conn.commit()
        await update.message.reply_text(f"Напоминание '{reminder_text}' установлено на {reminder_time.strftime('%H:%M')}!")
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text("Произошла ошибка при сохранении напоминания. Пожалуйста, попробуйте еще раз.")
    finally:
        cur.close()
        conn.close()

    return await menu(update, context)

# Обработчик отметки выполнения привычки
async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, habit_name FROM habits WHERE user_id = %s", (user_id,))
    habits = cur.fetchall()
    cur.close()
    conn.close()
    
    if not habits:
        await update.message.reply_text("У вас пока нет добавленных привычек. Используйте /menu для возврата в главное меню.")
        return ConversationHandler.END
    
    habit_keyboard = [[habit[1]] for habit in habits]
    habit_keyboard.append(["/menu"])
    await update.message.reply_text(
        "Какую привычку вы выполнили? (Или используйте /menu для возврата в главное меню)",
        reply_markup=ReplyKeyboardMarkup(habit_keyboard, one_time_keyboard=True),
    )
    return TYPING_HABIT_DONE
# Сохранение выполнения привычки
async def save_habit_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    habit_name = update.message.text
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM habits WHERE user_id = %s AND habit_name = %s", (user_id, habit_name))
    habit_id = cur.fetchone()
    if habit_id:
        cur.execute("INSERT INTO habit_logs (habit_id) VALUES (%s)", (habit_id[0],))
        conn.commit()
        await update.message.reply_text(f"Отлично! Привычка '{habit_name}' отмечена как выполненная.")
    else:
        await update.message.reply_text("Извините, такая привычка не найдена.")
    cur.close()
    conn.close()
    return await menu(update, context)

def recreate_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DROP TABLE IF EXISTS habit_logs")
        cur.execute("DROP TABLE IF EXISTS habits")
        cur.execute("DROP TABLE IF EXISTS reminders")
        
        cur.execute('''
            CREATE TABLE habits (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                habit_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                reminder_text TEXT NOT NULL,
                reminder_time TIMESTAMP NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE habit_logs (
                id SERIAL PRIMARY KEY,
                habit_id INTEGER NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (habit_id) REFERENCES habits (id)
            )
        ''')
        conn.commit()
        print("Tables recreated successfully")
    except psycopg2.Error as e:
        print(f"Error recreating tables: {e}")
    finally:
        cur.close()
        conn.close()

# Обработчик запроса статистики
async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT h.habit_name, COUNT(hl.id) as count
        FROM habits h
        LEFT JOIN habit_logs hl ON h.id = hl.habit_id
        WHERE h.user_id = %s
        GROUP BY h.id, h.habit_name
    """, (user_id,))
    stats = cur.fetchall()
    cur.close()
    conn.close()
    
    if not stats:
        await update.message.reply_text(
            "У вас пока нет статистики по привычкам.\n"
            "Используйте /menu для возврата в главное меню."
        )
    else:
        stats_text = "Статистика по вашим привычкам:\n\n"
        for habit, count in stats:
            stats_text += f"{habit}: выполнено {count} раз\n"
        stats_text += "\nИспользуйте /menu для возврата в главное меню."
        await update.message.reply_text(stats_text)
    
    return await menu(update, context)

async def get_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT habit_name FROM habits WHERE user_id = %s", (user_id,))
    habits = cur.fetchall()
    
    cur.execute("SELECT reminder_text, reminder_time FROM reminders WHERE user_id = %s", (user_id,))
    reminders = cur.fetchall()
    
    cur.close()
    conn.close()
    
    response = "Ваши привычки:\n"
    if habits:
        for habit in habits:
            response += f"- {habit[0]}\n"
    else:
        response += "У вас пока нет добавленных привычек.\n"
    
    response += "\nВаши напоминания:\n"
    if reminders:
        for reminder in reminders:
            response += f"- {reminder[0]} в {reminder[1].strftime('%H:%M %d.%m.%Y')}\n"
    else:
        response += "У вас пока нет установленных напоминаний.\n"
    
    response += "\nИспользуйте /menu для возврата в главное меню."
    
    await update.message.reply_text(response)
    return await menu(update, context)

def main() -> None:
    # Создание таблиц в базе данных
    # create_tables()
    recreate_tables()

    # Создание и настройка приложения
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    # Добавление обработчиков команд
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [
                MessageHandler(filters.Regex('^Добавить привычку$'), add_habit),
                MessageHandler(filters.Regex('^Установить напоминание$'), set_reminder),
                MessageHandler(filters.Regex('^Отметить выполнение$'), mark_done),
                MessageHandler(filters.Regex('^Статистика$'), get_stats),
                MessageHandler(filters.Regex('^Список привычек и напоминаний$'), get_list),
            ],
            TYPING_HABIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_habit),
                CommandHandler('menu', menu),
            ],
            TYPING_REMINDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_reminder),
                CommandHandler('menu', menu),
            ],
            TYPING_HABIT_DONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_habit_done),
                CommandHandler('menu', menu),
            ],
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('menu', menu)],
    )
    application.add_error_handler(error_handler)

    application.add_handler(conv_handler)
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
