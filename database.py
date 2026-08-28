import asyncpg

DB_URL = "postgresql://neondb_owner:npg_fWjluDvkZJ61@ep-blue-star-ay2wc9j2-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require"

async def get_pool():
    pool = await asyncpg.create_pool(DB_URL)
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kbkh_pairs (
                id SERIAL PRIMARY KEY,
                unique_id VARCHAR,
                phone_number VARCHAR
            )
        """)
    return pool

# ================= ADMIN SETTINGS =================
async def get_event_status(pool):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT event_status FROM admin_settings WHERE id = 1")

async def toggle_event_status(pool, status: bool):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE admin_settings SET event_status = $1 WHERE id = 1", status)

async def insert_paired_numbers(pool, nums):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM kbkh_pairs ORDER BY id ASC")
        for i, num in enumerate(nums):
            if i < len(rows):
                await conn.execute("UPDATE kbkh_pairs SET phone_number = $1 WHERE id = $2", num, rows[i]['id'])
            else:
                await conn.execute("INSERT INTO kbkh_pairs (phone_number) VALUES ($1)", num)

async def insert_paired_ids(pool, ids):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM kbkh_pairs ORDER BY id ASC")
        for i, uid in enumerate(ids):
            if i < len(rows):
                await conn.execute("UPDATE kbkh_pairs SET unique_id = $1 WHERE id = $2", uid, rows[i]['id'])
            else:
                await conn.execute("INSERT INTO kbkh_pairs (unique_id) VALUES ($1)", uid)

async def check_valid_unique_id(pool, unique_id):
    async with pool.acquire() as conn:
        res = await conn.fetchval("SELECT unique_id FROM kbkh_pairs WHERE unique_id = $1", unique_id)
        return bool(res)

async def check_phone_for_id(pool, unique_id, phone):
    async with pool.acquire() as conn:
        expected = await conn.fetchval("SELECT phone_number FROM kbkh_pairs WHERE unique_id = $1", unique_id)
        return expected == phone

async def reset_all_data(pool):
    async with pool.acquire() as conn:
        try:
            # একদম A-Z সব মুছে ফ্রেশ করার কমান্ড
            await conn.execute("TRUNCATE memes, users, kbkh_pairs RESTART IDENTITY CASCADE;")
        except:
            pass
        await conn.execute("UPDATE admin_settings SET event_status = TRUE WHERE id = 1")

# ================= USERS & MODERATORS =================
async def get_user(pool, tg_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", tg_id)

async def register_user(pool, tg_id, unique_id, phone, role):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, unique_id, phone_number, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_id) DO UPDATE SET unique_id=$2, phone_number=$3, role=$4
        """, tg_id, unique_id, phone, role)

# ================= MEME SUBMISSION =================
async def get_meme_count(pool, tg_id):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM memes WHERE member_tg_id = $1", tg_id)

async def add_meme(pool, tg_id, file_id):
    async with pool.acquire() as conn:
        # মডারেটর ফিক্সড করা, যেন ৫টি মিম একজন মডারেটরের কাছেই যায়
        mod_id = await conn.fetchval("SELECT assigned_mod_tg_id FROM memes WHERE member_tg_id = $1 LIMIT 1", tg_id)
        if not mod_id:
            mod_id = await conn.fetchval("""
                SELECT telegram_id FROM users 
                WHERE role = 'MODERATOR' 
                ORDER BY (SELECT COUNT(DISTINCT member_tg_id) FROM memes WHERE assigned_mod_tg_id = users.telegram_id) ASC 
                LIMIT 1
            """)
        await conn.execute("""
            INSERT INTO memes (file_id, member_tg_id, assigned_mod_tg_id)
            VALUES ($1, $2, $3)
        """, file_id, tg_id, mod_id)

# ================= MODERATOR MARKING =================
async def get_pending_candidates(pool, mod_tg_id):
    async with pool.acquire() as conn:
        # ৫টি মিম সাবমিট ও মার্কিং না হওয়া পর্যন্ত লিস্টে দেখাবে 
        return await conn.fetch("""
            SELECT u.unique_id, SUM(CASE WHEN m.is_marked = FALSE THEN 1 ELSE 0 END) as pending_count 
            FROM memes m JOIN users u ON m.member_tg_id = u.telegram_id
            WHERE m.assigned_mod_tg_id = $1
            GROUP BY u.unique_id 
            HAVING COUNT(m.meme_id) < 5 OR SUM(CASE WHEN m.is_marked = FALSE THEN 1 ELSE 0 END) > 0
            ORDER BY MIN(m.meme_id) ASC
        """, mod_tg_id)

async def get_marked_candidates(pool, mod_tg_id):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT u.unique_id, COUNT(m.meme_id) as marked_count 
            FROM memes m JOIN users u ON m.member_tg_id = u.telegram_id
            WHERE m.assigned_mod_tg_id = $1 AND m.is_marked = TRUE
            GROUP BY u.unique_id ORDER BY MIN(m.meme_id) ASC
        """, mod_tg_id)

async def get_memes_for_candidate(pool, mod_tg_id, unique_id, is_marked):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT m.meme_id, m.file_id, m.mark 
            FROM memes m JOIN users u ON m.member_tg_id = u.telegram_id
            WHERE m.assigned_mod_tg_id = $1 AND u.unique_id = $2 AND m.is_marked = $3
            ORDER BY m.meme_id ASC
        """, mod_tg_id, unique_id, is_marked)

async def mark_meme(pool, meme_id, mark):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE memes SET mark = $1, is_marked = TRUE WHERE meme_id = $2", mark, meme_id)

# ================= ADMIN RESULTS =================
async def get_final_results(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT u.unique_id, SUM(m.mark) as total_mark, MAX(m.is_selected_by_admin::int) as is_selected
            FROM memes m JOIN users u ON m.member_tg_id = u.telegram_id
            WHERE m.is_marked = TRUE
            GROUP BY u.unique_id ORDER BY total_mark DESC
        """)

async def toggle_admin_selection(pool, unique_id):
    async with pool.acquire() as conn:
        current_status = await conn.fetchval("""
            SELECT is_selected_by_admin FROM memes 
            WHERE member_tg_id = (SELECT telegram_id FROM users WHERE unique_id = $1 LIMIT 1) LIMIT 1
        """, unique_id)
        new_status = not current_status
        await conn.execute("""
            UPDATE memes SET is_selected_by_admin = $1 
            WHERE member_tg_id = (SELECT telegram_id FROM users WHERE unique_id = $2)
        """, new_status, unique_id)

async def get_selected_members(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT DISTINCT u.telegram_id, u.unique_id FROM users u
            JOIN memes m ON u.telegram_id = m.member_tg_id
            WHERE m.is_selected_by_admin = TRUE
        """)

async def get_all_members_marks(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT u.telegram_id, SUM(m.mark) as total_mark 
            FROM users u JOIN memes m ON u.telegram_id = m.member_tg_id
            WHERE m.is_marked = TRUE
            GROUP BY u.telegram_id
        """)
