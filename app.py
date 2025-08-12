import os
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai
import psycopg2
import json
from psycopg2.extras import Json
import urllib.parse

app = Flask(__name__)

# --- CONFIGURAÇÕES IMPORTANTES ---

# As chaves e URLs são variáveis de ambiente no Render.
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("A variável de ambiente GOOGLE_API_KEY não foi configurada.")
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("A variável de ambiente DATABASE_URL não foi configurada.")

WAHA_URL = os.environ.get('WAHA_URL')
if not WAHA_URL:
    raise ValueError("A variável de ambiente WAHA_URL não foi configurada.")

MAX_HISTORY_MESSAGES = 10 

# --- FLUXO DE CONVERSA (MÁQUINA DE ESTADOS) ---
STATE_MENU = "menu_principal"
STATE_FRANCHISE_Q1 = "franquia_q1_nome"
STATE_FRANCHISE_Q2 = "franquia_q2_email"
STATE_FRANCHISE_Q3 = "franquia_q3_tel"
STATE_FRANCHISE_Q4 = "franquia_q4_cidade"
STATE_FRANCHISE_Q5 = "franquia_q5_estado"
STATE_FRANCHISE_Q6 = "franquia_q6_data"
STATE_FRANCHISE_Q7 = "franquia_q7_capital"
STATE_RESELLER_Q1 = "revendedor_q1_nome"
STATE_RESELLER_Q2 = "revendedor_q2_email"
STATE_RESELLER_Q3 = "revendedor_q3_tel"
STATE_RESELLER_Q4 = "revendedor_q4_cidade"
STATE_RESELLER_Q5 = "revendedor_q5_estado"
STATE_RESELLER_Q6 = "revendedor_q6_loja"
STATE_RESELLER_Q7 = "revendedor_q7_negocio"
STATE_GENERAL_CHAT = "chat_geral"

# --- MENSAGENS PADRONIZADAS ---
MENU_TEXT = """
📋 𝑺𝒑𝒊𝒓𝒊𝒕𝒐 𝑺𝒂𝒏𝒕𝒐 - Menu de Opções
1️⃣ Problemas com produto  
2️⃣ Seja Franqueado  
3️⃣ Virar Revendedor  
4️⃣ Sobre a Spirito Santo  
Digite o número da opção desejada.
"""
GREETING = "Olá! 👋 Sou o assistente virtual da Spirito Santo."

PROBLEMS_TEXT = """
⚠ Suporte ao Cliente  
Para resolver seu problema mais rápido, fale diretamente com nosso atendimento humano no WhatsApp:  
👉 https://web.whatsapp.com/send/?phone=5551981938778&text&source&data&app_absent

Por favor, envie:  
- Foto do produto  
- Descrição do problema  

⏰ Atendimento: Seg-Sex: 10h às 19h | Sáb: 10h às 17h
"""
FRANCHISE_START_TEXT = "🧑‍💼 Que ótimo o seu interesse em abrir uma franquia conosco! Para que possamos te enviar a apresentação completa, precisamos de alguns dados seus."
FRANCHISE_Q_1 = "1️⃣ Qual é o seu nome completo?"
FRANCHISE_Q_2 = "2️⃣ Qual é o seu e-mail?"
FRANCHISE_Q_3 = "3️⃣ Qual é o seu telefone/WhatsApp?"
FRANCHISE_Q_4 = "4️⃣ Em qual cidade pretende abrir a franquia?"
FRANCHISE_Q_5 = "5️⃣ Qual é o estado dessa cidade?"
FRANCHISE_Q_6 = "6️⃣ Qual a data prevista para iniciar o projeto? (mês/ano)"
FRANCHISE_Q_7 = """
7️⃣ Qual capital disponível para investimento?
   Digite uma opção:
   1 - Entre R$ 200 mil e R$ 275 mil
   2 - Acima de R$ 350 mil
"""
FRANCHISE_END_TEXT = "Obrigado! Aqui está a apresentação completa do nosso projeto de franquias:\n\nhttps://sults-bucket.s3.amazonaws.com/spiritosanto/ProjetoTarefa/2170/Novo_Projeto_de_Franquias_2.0_.pdf"
FRANCHISE_CAPITAL_OPTIONS = {
    '1': "Entre R$ 200 mil e R$ 275 mil",
    '2': "Acima de R$ 350 mil"
}
RESELLER_START_TEXT = "🤝 Que ótimo o seu interesse em revender nossos produtos! Antes de enviarmos nossa tabela de preços e condições, precisamos de algumas informações:"
RESELLER_Q_1 = "1️⃣ Qual é o seu nome completo?"
RESELLER_Q_2 = "2️⃣ Qual é o seu e-mail?"
RESELLER_Q_3 = "3️⃣ Qual é o seu telefone/WhatsApp?"
RESELLER_Q_4 = "4️⃣ Qual é a sua cidade?"
RESELLER_Q_5 = "5️⃣ Qual é o estado da sua cidade?"
RESELLER_Q_6 = "6️⃣ Você já possui loja ou pretende iniciar?"
RESELLER_Q_7 = "7️⃣ Qual é o seu tipo de negócio? (Loja física, online, ambos, outro)"
RESELLER_END_TEXT = "Perfeito! Aqui está nossa tabela de preços e condições para revendedores:\n\nhttps://sults-bucket.s3.amazonaws.com/spiritosanto/ProjetoTarefa/2170/Novo_Projeto_de_Franquias_2.0_.pdf"
ABOUT_TEXT = """
🌟 SOBRE A SPIRITO SANTO
Fundada em 2006 por Andreas & Frederico Renner Mentz.
📍 Lojas: IGUATEMI, MOINHOS, CANOAS, CAXIAS, ERECHIM, IJUÍ, PASSO FUNDO, PELOTAS, RIO GRANDE, SANTA MARIA, BARRA, PRAIA e MATRIZ.
👔 Moda urbana com atitude, casual e social.
🌐 www.spiritosanto.com.br | 📸 @spiritosanto
📦 Entregas em todo o Brasil.
"""
REDIRECT_TO_MENU_TEXT = "Desculpe, não entendi. Digite um número do menu para continuar."

# Base de conhecimento para a IA
STORE_INFO = ABOUT_TEXT + """
A Spirito Santo é uma marca de moda masculina contemporânea.
... (Adicione aqui mais informações da sua loja para o Gemini) ...
"""

# --- Funções do Banco de Dados ---

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        return None

def create_tables():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_state (
                chat_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                data JSONB,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cursor.close()
        conn.close()

create_tables()

def get_user_state(chat_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT state, data FROM user_state WHERE chat_id = %s", (chat_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result:
            return result[0], result[1] or {}
    return STATE_MENU, {}

def set_user_state(chat_id, state, data=None):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        if data is None:
            data = {}
        cursor.execute(
            "INSERT INTO user_state (chat_id, state, data) VALUES (%s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data",
            (chat_id, state, Json(data))
        )
        conn.commit()
        cursor.close()
        conn.close()
def save_message(chat_id, sender, message):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (chat_id, sender, message) VALUES (%s, %s, %s)",
            (chat_id, sender, message)
        )
        conn.commit()
        cursor.close()
        conn.close()

def get_chat_history(chat_id):
    conn = get_db_connection()
    history = []
    if conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sender, message FROM messages WHERE chat_id = %s ORDER BY timestamp DESC LIMIT %s",
            (chat_id, MAX_HISTORY_MESSAGES)
        )
        history = cursor.fetchall()
        cursor.close()
        conn.close()
    return history[::-1]

def send_waha_message(chat_id, text):
    payload_reply = {
        "session": "default",
        "chatId": chat_id,
        "text": text
    }
    headers = {"Content-Type": "application/json"}
    try:
        requests.post(f"{WAHA_URL}/api/sendText", json=payload_reply, headers=headers)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem para o WAHA: {e}")

# --- Lógica da IA ---

def get_ia_response(user_message, chat_history):
    formatted_history = "".join([f"**{sender}:** {message}\n" for sender, message in chat_history])
    full_prompt = f"""
    Você é um assistente virtual da Spirito Santo. Use as seguintes informações para responder a perguntas:
    {STORE_INFO}
    
    **Histórico da Conversa:**
    {formatted_history}
    
    **Pergunta Atual:**
    {user_message}
    
    Responda em Português do Brasil de forma útil e amigável.
    """
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        print(f"Erro ao chamar a IA: {e}")
        return "Desculpe, não consegui processar sua solicitação no momento."

# --- WEBHOOK PRINCIPAL (COM A LÓGICA DO CHATBOT) ---

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data.get('event') == 'message' and 'payload' in data:
        payload = data['payload']
        sender = payload.get('from')
        text = payload.get('body', '').strip()

        # Ignora mensagens vazias ou do próprio bot
        if not text or sender == "status@broadcast":
            return jsonify({"status": "ignored"}), 200

        # Salva a mensagem recebida e pega o estado do usuário
        save_message(sender, 'user', text)
        user_state, user_data = get_user_state(sender)
        
        # --- Lógica de Roteamento ---

        if user_state == STATE_MENU:
            if text == "1":
                send_waha_message(sender, PROBLEMS_TEXT)
            elif text == "2":
                set_user_state(sender, STATE_FRANCHISE_Q1)
                send_waha_message(sender, FRANCHISE_START_TEXT + "\n\n" + FRANCHISE_Q_1)
            elif text == "3":
                set_user_state(sender, STATE_RESELLER_Q1)
                send_waha_message(sender, RESELLER_START_TEXT + "\n\n" + RESELLER_Q_1)
            elif text == "4":
                send_waha_message(sender, ABOUT_TEXT)
                send_waha_message(sender, MENU_TEXT)
            else: # Pergunta fora do menu
                chat_history = get_chat_history(sender)
                ia_response = get_ia_response(text, chat_history)
                send_waha_message(sender, ia_response)
                send_waha_message(sender, MENU_TEXT)
                save_message(sender, 'bot', ia_response)
        
        # Lógica de Franquia
        elif user_state.startswith("franquia"):
            current_q_num = int(user_state[-1])
            user_data[f"q{current_q_num}"] = text
            
            if current_q_num < 7:
                next_state = f"franquia_q{current_q_num + 1}"
                next_question = globals()[f"FRANCHISE_Q_{current_q_num + 1}"]
                send_waha_message(sender, next_question)
                set_user_state(sender, next_state, user_data)
            else: # Última pergunta de Franquia
                if text in FRANCHISE_CAPITAL_OPTIONS:
                    user_data["q7"] = FRANCHISE_CAPITAL_OPTIONS[text]
                
                send_waha_message(sender, FRANCHISE_END_TEXT)
                # Opcional: Salvar o lead em outro lugar
                send_waha_message(sender, MENU_TEXT)
                set_user_state(sender, STATE_MENU)
        
        # Lógica de Revendedor
        elif user_state.startswith("revendedor"):
            current_q_num = int(user_state[-1])
            user_data[f"q{current_q_num}"] = text
            
            if current_q_num < 7:
                next_state = f"revendedor_q{current_q_num + 1}"
                next_question = globals()[f"RESELLER_Q_{current_q_num + 1}"]
                send_waha_message(sender, next_question)
                set_user_state(sender, next_state, user_data)
            else: # Última pergunta de Revendedor
                send_waha_message(sender, RESELLER_END_TEXT)
                # Opcional: Salvar o lead em outro lugar
                send_waha_message(sender, MENU_TEXT)
                set_user_state(sender, STATE_MENU)

    return jsonify({"status": "received"}), 200

@app.route('/')
def home():
    return "O bot Python está rodando e aguardando webhooks na rota /webhook."

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)