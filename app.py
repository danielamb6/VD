@app.route('/')
def index_page():
    return render_template('index2.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/registro')
def registro_page():
    return render_template('registro_usuario.html')

# --- ENDPOINT DE LOGIN (Verifica que lo tengas) ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db_connection()
    if not conn: return jsonify({"error": "No hay conexión a BD"}), 500
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM admin WHERE usuario = %s", (username,))
        user = cur.fetchone()
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['contrasena'].encode('utf-8')):
            user.pop('contrasena') # Seguridad
            return jsonify({"mensaje": "Login exitoso", "usuario": user}), 200
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    finally: conn.close()
