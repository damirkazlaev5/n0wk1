from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'supersecretkey'
socketio = SocketIO(app, cors_allowed_origins="*")

DB_PATH = 'database.db'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    conn.commit()
    conn.close()


@app.route('/')
def index():
    # Теперь главная страница — это index.html
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                      (username, generate_password_hash(password)))
            conn.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            error = 'Такой пользователь уже существует'
        finally:
            conn.close()
    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))  # Ведём на главную (index)
        else:
            error = 'Неверный логин или пароль'
    return render_template('login.html', error=error)


@app.route('/post', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    content = request.form.get('content')
    if not content or not content.strip():
        return redirect(url_for('index'))

    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO posts (user_id, content) VALUES (?, ?)',
              (session['user_id'], content))
    post_id = c.lastrowid
    conn.commit()

    c.execute('SELECT u.username, p.content, p.created_at FROM posts p JOIN users u ON p.user_id=u.id WHERE p.id=?',
              (post_id,))
    row = c.fetchone()
    conn.close()

    post = {
        'username': row['username'],
        'content': row['content'],
        'created_at': row['created_at']
    }
    socketio.emit('new_post', post)

    return redirect(url_for('index'))  # После поста возвращаемся на главную


@app.route('/api/posts')
def api_posts():
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT p.content, p.created_at, u.username FROM posts p
                 JOIN users u ON p.user_id = u.id ORDER BY p.created_at DESC LIMIT 50''')
    posts = [dict(row) for row in c.fetchall()]
    conn.close()
    return {'posts': posts}


if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True)
