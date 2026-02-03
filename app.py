from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import bcrypt

app = Flask(__name__)
CORS(app)

# --- CONFIGURACIÓN BD (¡IMPORTANTE! AJUSTA TUS CREDENCIALES AQUÍ) ---
# Si usas local, usa esta estructura:
#DB_URI = 'postgresql://postgres:TU_CONTRASEÑA@localhost:5432/postgres' 
# Si usas la nube (Neon), descomenta y usa la tuya:
DB_URI = 'postgresql://neondb_owner:npg_LOQTwP86bvYc@ep-floral-meadow-ahobjrmx-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require'

def get_db_connection():
    try:
        conn = psycopg2.connect(DB_URI)
        return conn
    except Exception as e:
        print(f"❌ Error conectando a BD: {e}")
        return None

@app.route('/', methods=['GET'])
def index():
    return "API Funcionando Correctamente"

# ==========================================
# 1. TICKETS E INCIDENCIAS
# ==========================================
@app.route('/api/tickets', methods=['GET'])
def get_tickets():
    conn = get_db_connection()
    if not conn: return jsonify({"error": "No hay conexión a BD"}), 500
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Se agregan JOINs para asegurar que se traigan datos aunque falten relaciones
        query = """
            SELECT 
                t.id, 
                t.num_autobus, 
                t.estado, 
                to_char(t.fecha_creacion, 'YYYY-MM-DD') as fecha_creacion,
                fr.falla as falla_descripcion,
                CONCAT(tec.nombre, ' ', tec.primer_apellido) as tecnico_nombre,
                CONCAT(c.nombre, ' ', c.primer_apellido) as cliente, 
                e.empresa as empresa_nombre
            FROM tickets t
            LEFT JOIN falla_reportada fr ON t.id_falla_reportada = fr.id
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            LEFT JOIN fichas_tecnicas ft ON t.id = ft.id_ticket
            LEFT JOIN tecnicos tec ON ft.id_tecnico = tec.id
            ORDER BY t.fecha_creacion DESC
        """
        cur.execute(query)
        data = cur.fetchall()
        return jsonify(data)
    except Exception as e:
        print(f"Error Tickets: {e}")
        return jsonify({"error": str(e)}), 500
    finally: conn.close()

@app.route('/api/tickets/<int:id>/estado', methods=['PUT'])
def cambiar_estado_ticket(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        nuevo_estado = request.json.get('estado')
        cur.execute("UPDATE tickets SET estado = %s WHERE id = %s", (nuevo_estado, id))
        conn.commit()
        return jsonify({"message": "Estado actualizado"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: conn.close()

# ==========================================
# 2. CATÁLOGOS (Visualización Corregida)
# ==========================================
@app.route('/api/catalogos/<tabla>', methods=['GET'])
def get_catalogos(tabla):
    conn = get_db_connection()
    if not conn: return jsonify([]), 500
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Mapeo exacto a tu Base de Datos SQL
    config = {
        'empresas':         {'t': 'empresas',         'col': 'empresa'},
        'equipo':           {'t': 'equipo',           'col': 'equipo'}, 
        'cat_elementos':    {'t': 'cat_elementos',    'col': 'elemento'},
        'accesorios':       {'t': 'accesorios',       'col': 'accesorio'}, # Corregido segun tu SQL
        'detalle_revision': {'t': 'detalle_revision', 'col': 'descripcion'},
        'solucion':         {'t': 'solucion',         'col': 'solucion'},
        'falla_reportada':  {'t': 'falla_reportada',  'col': 'falla'}
    }

    if tabla not in config:
        return jsonify({"error": "Tabla no configurada"}), 400
    
    table_name = config[tabla]['t']
    col_name = config[tabla]['col']

    try:
        # Consulta dinámica simple para visualizar
        query = f'SELECT id, "{col_name}" as descripcion FROM "{table_name}" ORDER BY id ASC'
        cur.execute(query)
        return jsonify(cur.fetchall())
    except Exception as e:
        print(f"Error catalogo {tabla}: {e}")
        return jsonify({"error": str(e)}), 500
    finally: conn.close()

@app.route('/api/catalogos/<tabla>', methods=['POST'])
def add_catalogo(tabla):
    # NOTA: Esto solo funcionará para tablas sin llaves foráneas obligatorias (como Empresas).
    # Para Equipos, Elementos, etc., necesitarías enviar el ID padre desde el Frontend.
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        valor = request.json.get('valor')
        
        if tabla == 'empresas':
            cur.execute('INSERT INTO empresas (empresa) VALUES (%s)', (valor,))
        elif tabla == 'falla_reportada': 
            # Requiere equipo, insertamos un default o null si la BD lo permite (Tu SQL dice NOT NULL)
            # Por ahora fallará si no modificamos la lógica completa para recibir id_equipo
            return jsonify({"error": "Falta seleccionar equipo padre"}), 400
        else:
             # Intento genérico para tablas simples
             return jsonify({"error": "Inserción simple no soportada para esta tabla compleja"}), 400
             
        conn.commit()
        return jsonify({"message": "Agregado"}), 201
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: conn.close()

@app.route('/api/catalogos/<tabla>/<int:id>', methods=['DELETE'])
def delete_catalogo(tabla, id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Mapeo simple de nombres para seguridad
        valid_tables = ['empresas', 'equipo', 'cat_elementos', 'accesorios', 'detalle_revision', 'solucion', 'falla_reportada']
        if tabla in valid_tables:
            cur.execute(f'DELETE FROM "{tabla}" WHERE id = %s', (id,))
            conn.commit()
            return jsonify({"message": "Eliminado"}), 200
        return jsonify({"error": "Tabla inválida"}), 400
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: conn.close()

# ==========================================
# 3. TÉCNICOS Y CLIENTES
# ==========================================
@app.route('/api/tecnicos', methods=['GET'])
def get_tecnicos():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # JOIN con especialidad para ver el nombre
        query = """
            SELECT t.id, t.nombre, t.primer_apellido, t.activo, e.especialidad 
            FROM tecnicos t 
            LEFT JOIN especialidad e ON t.id_especialidad = e.id 
            ORDER BY t.id
        """
        cur.execute(query)
        return jsonify(cur.fetchall())
    finally: conn.close()

@app.route('/api/clientes', methods=['GET'])
def get_clientes():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
            SELECT c.id, c.nombre, c.primer_apellido, c.activo, e.empresa 
            FROM cliente c 
            LEFT JOIN empresas e ON c.id_empresa = e.id 
            ORDER BY c.id
        """
        cur.execute(query)
        return jsonify(cur.fetchall())
    finally: conn.close()

@app.route('/api/<tipo>/<int:id>/toggle', methods=['PUT'])
def toggle_estado(tipo, id):
    table_map = {'tecnicos': 'tecnicos', 'clientes': 'cliente', 'admin': 'admin'}
    if tipo not in table_map: return jsonify({"error": "Tipo inválido"}), 400
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE {table_map[tipo]} SET activo = NOT activo WHERE id = %s", (id,))
        conn.commit()
        return jsonify({"message": "OK"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: conn.close()

# ==========================================
# 4. ADMIN USUARIOS
# ==========================================
@app.route('/api/admin', methods=['GET', 'POST'])
def admin_users():
    conn = get_db_connection()
    if not conn: return jsonify([]), 500
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            cur.execute("SELECT * FROM admin ORDER BY id DESC")
            return jsonify(cur.fetchall())
        
        if request.method == 'POST':
            d = request.json
            # Hash password simple para demo, en prod usar bcrypt completo
            hashed = bcrypt.hashpw(d['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            cur.execute("""
                INSERT INTO admin (nombre, primer_apellido, correo, rol, usuario, contrasena, activo)
                VALUES (%s, '', %s, %s, %s, %s, TRUE)
            """, (d['nombre'], d['email'], d['rol'], d['username'], hashed))
            conn.commit()
            return jsonify({"message": "Creado"}), 201
            
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: conn.close()

@app.route('/api/admin/<int:id>/estado', methods=['PUT'])
def toggle_admin(id):
    return toggle_estado('admin', id)

# ==========================================
# 5. REPORTES (Simplificado para evitar errores)
# ==========================================
# --- EN app.py, REEMPLAZA LA RUTA DE REPORTES CON ESTO ---

@app.route('/api/reportes/generar', methods=['POST'])
def generar_reporte():
    filtros = request.json
    conn = get_db_connection()
    if not conn: return jsonify({"error": "Error BD"}), 500
    
    # Estructura base para que el frontend no falle si no hay datos
    response_data = {
        "tickets_stats": [], 
        "tickets_lista": [], 
        "fichas_stats": {
            "top_equipos": [], 
            "top_fallas": [], 
            "tiempos_resolucion": []
        }, 
        "refacciones_stats": {
            "estatus": [], 
            "tiempos": [], 
            "total_global": 0
        },
        "extra_stats": {"total": 0, "lista": []}
    }
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # --- 1. FILTROS SQL ---
        where_clauses = ["1=1"] # Siempre verdadero para facilitar concatenación
        params = []
        if filtros.get('fecha_ini'): 
            where_clauses.append("t.fecha_creacion >= %s")
            params.append(filtros['fecha_ini'])
        if filtros.get('fecha_fin'): 
            where_clauses.append("t.fecha_creacion <= %s")
            params.append(filtros['fecha_fin'])
        if filtros.get('estado'): 
            where_clauses.append("t.estado = %s")
            params.append(filtros['estado'])
        if filtros.get('empresa'): 
            where_clauses.append("e.empresa = %s")
            params.append(filtros['empresa'])
            
        where_str = " AND ".join(where_clauses)
        
        # --- 2. DATOS DE TICKETS ---
        # Estadísticas por estado
        cur.execute(f"""
            SELECT t.estado, COUNT(*) as total FROM tickets t
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            WHERE {where_str} 
            GROUP BY t.estado
        """, tuple(params))
        response_data['tickets_stats'] = cur.fetchall()

        # Lista detallada
        cur.execute(f"""
            SELECT t.id, t.num_autobus, t.fecha_creacion, t.estado, e.empresa, CONCAT(c.nombre, ' ', c.primer_apellido) as cliente
            FROM tickets t
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            WHERE {where_str} 
            ORDER BY t.fecha_creacion DESC
        """, tuple(params))
        tickets = cur.fetchall()
        for t in tickets: t['fecha_creacion'] = str(t['fecha_creacion'])
        response_data['tickets_lista'] = tickets

        # --- 3. DATOS DE FICHAS TÉCNICAS (GRÁFICAS) ---
        try:
            # Top Equipos con fallas
            cur.execute("""
                SELECT eq.equipo, COUNT(*) as fallas 
                FROM tickets t
                JOIN falla_reportada fr ON t.id_falla_reportada = fr.id
                JOIN equipo eq ON fr.id_equipo = eq.id
                GROUP BY eq.equipo 
                ORDER BY fallas DESC LIMIT 5
            """)
            response_data['fichas_stats']['top_equipos'] = cur.fetchall()

            # Top Tipos de Falla
            cur.execute("""
                SELECT fr.falla, COUNT(*) as cantidad
                FROM tickets t
                JOIN falla_reportada fr ON t.id_falla_reportada = fr.id
                GROUP BY fr.falla
                ORDER BY cantidad DESC LIMIT 10
            """)
            response_data['fichas_stats']['top_fallas'] = cur.fetchall()

            # Tiempos de Resolución (Calculado en horas)
            cur.execute("""
                SELECT 
                    t.id, 
                    t.fecha_creacion, 
                    ft.fecha_cierre, 
                    (ft.fecha_cierre - t.fecha_creacion) as duracion,
                    EXTRACT(EPOCH FROM (ft.fecha_cierre - t.fecha_creacion))/3600 as horas_aprox
                FROM tickets t 
                JOIN fichas_tecnicas ft ON t.id = ft.id_ticket
                WHERE t.estado = 'RESUELTO' AND ft.fecha_cierre IS NOT NULL
                ORDER BY t.id DESC LIMIT 10
            """)
            tiempos = cur.fetchall()
            for t in tiempos:
                t['fecha_creacion'] = str(t['fecha_creacion'])
                t['fecha_cierre'] = str(t['fecha_cierre'])
                t['duracion'] = str(t['duracion'])
            response_data['fichas_stats']['tiempos_resolucion'] = tiempos
            
        except Exception as e:
            print(f"⚠️ Warning Fichas: {e}") 
            # Si fallan las fichas, continuamos con lo demás

        # --- 4. DATOS DE REPORTES EXTRA ---
        try:
            cur.execute("SELECT COUNT(*) as total FROM reporte_extra")
            res_extra = cur.fetchone()
            total_extra = res_extra['total'] if res_extra else 0
            
            cur.execute("SELECT id, observacion FROM reporte_extra ORDER BY id DESC LIMIT 10")
            response_data['extra_stats'] = {'total': total_extra, 'lista': cur.fetchall()}
        except Exception as e: print(f"⚠️ Warning Extras: {e}")

        # --- 5. DATOS DE REFACCIONES ---
        try:
            cur.execute("""
                SELECT 
                    CASE WHEN fecha_cierre IS NOT NULL THEN 'CERRADO' ELSE 'ABIERTO' END as estado,
                    COUNT(*) as total 
                FROM reporte_refaccion GROUP BY estado
            """)
            response_data['refacciones_stats']['estatus'] = cur.fetchall()
            
            cur.execute("SELECT COUNT(*) as total FROM reporte_refaccion")
            res_ref = cur.fetchone()
            response_data['refacciones_stats']['total_global'] = res_ref['total'] if res_ref else 0
            
        except Exception as e: print(f"⚠️ Warning Refacciones: {e}")

        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Error General Reportes: {e}")
        return jsonify({"error": str(e)}), 500
    finally: conn.close()

if __name__ == '__main__':
    # host='0.0.0.0' permite acceso desde la red, pero debug=True es peligroso en prod.

    app.run(host='0.0.0.0', debug=True, port=5000)
