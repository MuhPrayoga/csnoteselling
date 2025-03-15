import streamlit as st
import mysql.connector

# Koneksi ke database
db = mysql.connector.connect(
    host="localhost",
    port=3306,
    user="root",
    password="",
    database="noteselling-wirpl"
)
cursor = db.cursor()

# Inisialisasi session state jika belum ada
if "role" not in st.session_state:
    st.session_state.role = None
if "username" not in st.session_state:
    st.session_state.username = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "cart" not in st.session_state:
    st.session_state.cart = []

role = st.session_state.role
username = st.session_state.username
user_id = st.session_state.user_id

# Sidebar Login / Registrasi
st.sidebar.title("Login / Registrasi")

if role is None:
    with st.sidebar.form("login_form"):
        username_input = st.text_input("Nama Pengguna")
        password_input = st.text_input("Password", type="password")
        login_btn = st.form_submit_button("Login")

    with st.sidebar.form("register_form"):
        new_username = st.text_input("Nama Pengguna Baru")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        role_selection = st.radio("Pilih Peran:", ["BUYER", "SELLER"])
        register_btn = st.form_submit_button("Registrasi")

    if login_btn:
        cursor.execute("SELECT user_id, role, password, is_verified FROM users WHERE username = %s", (username_input,))
        user = cursor.fetchone()
        if user and user[2] == password_input:
            if user[3] == 'TRUE':
                st.session_state.update({
                    "role": user[1],
                    "username": username_input,
                    "user_id": user[0]
                })
                st.rerun()
            else:
                st.sidebar.error("Akun belum diverifikasi. Silakan cek email Anda.")
        else:
            st.sidebar.error("Nama pengguna atau password salah. Silakan coba lagi.")

    if register_btn:
        cursor.execute("SELECT * FROM users WHERE username = %s", (new_username,))
        existing_user = cursor.fetchone()
        if existing_user:
            st.sidebar.error("Nama pengguna sudah terdaftar, silakan pilih nama lain.")
        else:
            cursor.execute("INSERT INTO users (username, email, password, role, is_verified) VALUES (%s, %s, %s, %s, 'FALSE')", (new_username, email, password, role_selection))
            db.commit()
            st.sidebar.success("Registrasi berhasil! Silakan cek email untuk verifikasi.")
            st.rerun()
else:
    st.sidebar.write(f"Login sebagai: {username} ({role})")
    if st.sidebar.button("Logout"):
        st.session_state.role = None
        st.session_state.username = None
        st.session_state.user_id = None
        st.session_state.cart = []
        st.rerun()

if role == "BUYER":
    st.title("Dashboard BUYER")
    search_query = st.text_input("Cari Mata Kuliah atau Materi")

    # Ambil daftar mata kuliah
    cursor.execute("SELECT course_id, course_name FROM courses ORDER BY course_name")
    courses = cursor.fetchall()
    course_dict = {course[0]: course[1] for course in courses}
    selected_course_id = st.selectbox("Pilih Mata Kuliah", list(course_dict.keys()), format_func=lambda x: course_dict[x])

    # Ambil daftar materi berdasarkan mata kuliah
    query = "SELECT material_id, title, price, file_path, seller_id FROM materials WHERE course_id = %s"
    params = (selected_course_id,)

    if search_query:
        query += " AND (title LIKE %s)"
        params += (f"%{search_query}%",)

    cursor.execute(query, params)
    materials_list = cursor.fetchall()

    # Tampilkan daftar materi
    for material in materials_list:
        cursor.execute("SELECT username FROM users WHERE user_id = %s", (material[4],))
        seller_name = cursor.fetchone()
        seller_display = seller_name[0] if seller_name else "Unknown"

        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"{material[1]} (Penjual: {seller_display})")
        with col2:
            if st.button(f'Beli - Rp {material[2]}', key=f'beli_{material[0]}'):
                st.session_state.cart.append(material)
                st.success(f'{material[1]} ditambahkan ke keranjang!')

    # Sidebar: Saldo
    st.sidebar.subheader("💰 Wallet")
    cursor.execute("SELECT balance FROM wallets WHERE user_id = %s", (user_id,))
    wallet = cursor.fetchone()
    balance = wallet[0] if wallet else 0
    st.sidebar.write(f"Saldo: Rp {balance}")

    # Tambah Saldo
    tambah_saldo = st.sidebar.number_input("Tambah Saldo (Rp)", min_value=0, step=1000)
    if st.sidebar.button("Isi Saldo"):
        if tambah_saldo > 0:
            if wallet:
                cursor.execute("UPDATE wallets SET balance = balance + %s WHERE user_id = %s", (tambah_saldo, user_id))
            else:
                cursor.execute("INSERT INTO wallets (user_id, balance) VALUES (%s, %s)", (user_id, tambah_saldo))
            db.commit()
            st.success("Saldo berhasil ditambahkan!")
            st.rerun()
        else:
            st.error("Masukkan jumlah saldo yang valid!")

    # Sidebar: Keranjang Belanja
    st.sidebar.subheader("🛒 Keranjang Belanja")
    for item in st.session_state.cart:
        st.sidebar.write(f'{item[1]} - Rp {item[2]}')

    bayar_sekarang = st.sidebar.button("Bayar Sekarang")
    bayar_nanti = st.sidebar.button("Bayar Nanti")

    if bayar_sekarang or bayar_nanti:
        total_harga = sum(item[2] for item in st.session_state.cart)
        
        # Tentukan status pembayaran
        if bayar_nanti or balance < total_harga:
            payment_status = "PENDING"
        else:
            payment_status = "COMPLETED"

        # Masukkan transaksi ke database
        transaction_ids = []
        for item in st.session_state.cart:
            cursor.execute("""
                INSERT INTO transactions (buyer_id, seller_id, material_id, amount, payment_status, transaction_date) 
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (user_id, item[4], item[0], item[2], payment_status))
            
            cursor.execute("SELECT LAST_INSERT_ID()")
            transaction_id = cursor.fetchone()[0]
            transaction_ids.append(transaction_id)
        
        db.commit()

        # Jika saldo cukup, lakukan pembayaran langsung
        if payment_status == "COMPLETED":
            cursor.execute("UPDATE wallets SET balance = balance - %s WHERE user_id = %s", (total_harga, user_id))
            for item in st.session_state.cart:
                cursor.execute("UPDATE wallets SET balance = balance + %s WHERE user_id = %s", (item[2], item[4]))
            db.commit()
            st.success("Transaksi berhasil!")
        else:
            st.warning("Saldo tidak mencukupi! Pembayaran ditandai sebagai 'PENDING'. Silakan bayar nanti.")

        st.session_state.cart.clear()
        st.rerun()

    # Pending Payments
    st.subheader("📌 Pending Payments")
    cursor.execute("SELECT transaction_id, amount FROM transactions WHERE buyer_id = %s AND payment_status = 'PENDING'", (user_id,))
    pending_payments = cursor.fetchall()
    
    if not pending_payments:
        st.write("Tidak ada pembayaran tertunda.")
    
    for payment in pending_payments:
        if st.button(f"Bayar Sekarang - Rp {payment[1]}", key=f"pay_{payment[0]}"):
            cursor.execute("SELECT balance FROM wallets WHERE user_id = %s", (user_id,))
            wallet = cursor.fetchone()
            balance = wallet[0] if wallet else 0

            if balance >= payment[1]:
                cursor.execute("UPDATE transactions SET payment_status = 'COMPLETED' WHERE transaction_id = %s", (payment[0],))
                cursor.execute("UPDATE wallets SET balance = balance - %s WHERE user_id = %s", (payment[1], user_id))
                
                cursor.execute("SELECT seller_id FROM transactions WHERE transaction_id = %s", (payment[0],))
                seller = cursor.fetchone()
                if seller:
                    cursor.execute("UPDATE wallets SET balance = balance + %s WHERE user_id = %s", (payment[1], seller[0]))
                
                db.commit()
                st.success("Pembayaran berhasil!")
                st.rerun()
            else:
                st.error("Saldo tidak mencukupi untuk pembayaran ini.")

# Tutup koneksi database
cursor.close()
db.close()
