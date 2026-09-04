import psycopg2
import psycopg2.extras

# DB 접속 설정
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mywheel",
    "user": "mywheel",
    "password": "mywheel",
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    """서버 시작 시 필요한 테이블/컬럼이 없으면 생성"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. 회원 테이블 (PK: id)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. 게시글 테이블
            cur.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    content TEXT NOT NULL,
                    author VARCHAR(50) DEFAULT '익명',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                ALTER TABLE posts ADD COLUMN IF NOT EXISTS likes_count INTEGER DEFAULT 0;
            """)
            cur.execute("""
                ALTER TABLE posts ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0;
            """)
            cur.execute("""
                ALTER TABLE posts ADD COLUMN IF NOT EXISTS user_id INTEGER
                    REFERENCES users(id) ON DELETE SET NULL;
            """)

            # 3. 댓글 테이블
            cur.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    author VARCHAR(50) DEFAULT '익명',
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                ALTER TABLE comments ADD COLUMN IF NOT EXISTS user_id INTEGER
                    REFERENCES users(id) ON DELETE SET NULL;
            """)

            # 4. 좋아요 테이블 (post_id + user_id 조합이 유일해야 함 = 중복 좋아요 방지)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS likes (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (post_id, user_id)
                );
            """)

            conn.commit()
