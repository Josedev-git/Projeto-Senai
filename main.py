import sys
import os
import sqlite3
import serial 
from PyQt5 import uic, QtWidgets
from PyQt5.QtChart import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis
from PyQt5.QtCore import Qt, QTimer

# Configurações de Caminho
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "database", "eletricitys.db")

# --- CONEXÃO SERIAL (ESP32) ---
try:
    esp32 = serial.Serial('COM4', 115200, timeout=0.1)
    esp32.reset_input_buffer()
    print("ESP32 conectado com sucesso!")
except Exception as e:
    esp32 = None
    print(f"Aviso: ESP32 não detectado (COM4).")

# --- BANCO DE DADOS ---
def iniciar_banco():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT, email TEXT UNIQUE, senha TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER, aparelho TEXT, potencia REAL,
            tempo REAL, consumo_kwh REAL, custo_reais REAL,
            data TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    con.commit()
    con.close()

usuario_logado = {"id": None, "nome": ""}

# Variável global para manter a instância da tela ativa viva na memória
tela_ativa = None

# ─────────────────────────────────────────────────────────────────────────────
# TELAS
# ─────────────────────────────────────────────────────────────────────────────

class TelaDashboard(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.join(BASE_DIR, "telas", "dashboard.ui"), self)
        self.showMaximized()
        self.btn_voltarinicio.clicked.connect(self.voltar_energia)
        self.btn_voltarhist.clicked.connect(self.abrir_historico)
        self.carregar_dados()

    def carregar_dados(self):
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT COALESCE(SUM(consumo_kwh),0), COALESCE(SUM(custo_reais),0) FROM historico WHERE usuario_id=?", (usuario_logado["id"],))
        total_kwh, total_reais = cur.fetchone()

        cur.execute("SELECT aparelho, SUM(consumo_kwh) FROM historico WHERE usuario_id=? GROUP BY aparelho ORDER BY 2 DESC LIMIT 5", (usuario_logado["id"],))
        dados_grafico = cur.fetchall()
        con.close()

        self.label_reais.setText(f"R$ {total_reais:.2f}")
        self.label_kwh_total.setText(f"{total_kwh:.3f} kWh")

        if dados_grafico:
            barras = QBarSet("kWh")
            nomes = []
            for aparelho, kwh in dados_grafico:
                barras.append(kwh)
                nomes.append(aparelho)
            serie = QBarSeries()
            serie.append(barras)
            grafico = QChart()
            grafico.addSeries(serie)
            grafico.setTitle("Consumo por Aparelho")
            eixo_x = QBarCategoryAxis()
            eixo_x.append(nomes)
            grafico.addAxis(eixo_x, Qt.AlignBottom)
            serie.attachAxis(eixo_x)
            eixo_y = QValueAxis()
            grafico.addAxis(eixo_y, Qt.AlignLeft)
            serie.attachAxis(eixo_y)
            view = QChartView(grafico)
            self.layout_grafico.addWidget(view)

    def voltar_energia(self):
        global tela_ativa
        tela_ativa = TelaEnergia()
        tela_ativa.show()
        self.close()

    def abrir_historico(self):
        global tela_ativa
        tela_ativa = TelaHistorico()
        tela_ativa.show()
        self.close()

class TelaHistorico(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.join(BASE_DIR, "telas", "historico.ui"), self)
        self.showMaximized()
        
        # --- MODIFICAÇÃO: Ajusta as colunas automaticamente para não cortar o texto ---
        self.tabela_aparelhos.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.tabela_aparelhos.horizontalHeader().setMinimumSectionSize(150)
        
        self.btn_voltarinicio.clicked.connect(self.voltar_energia)
        self.btn_voltardash.clicked.connect(self.abrir_dashboard)
        self.btn_limpar.clicked.connect(self.limpar_historico)
        self.carregar_tabela()

    def carregar_tabela(self):
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT aparelho, consumo_kwh, custo_reais FROM historico WHERE usuario_id = ? ORDER BY id DESC", (usuario_logado["id"],))
        rows = cur.fetchall(); con.close()
        tabela = self.tabela_aparelhos
        tabela.setRowCount(len(rows))
        for i, (ap, cons, cust) in enumerate(rows):
            tabela.setItem(i, 0, QtWidgets.QTableWidgetItem(ap))
            tabela.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{cons:.3f}"))
            tabela.setItem(i, 2, QtWidgets.QTableWidgetItem(f"R$ {cust:.2f}"))

    def limpar_historico(self):
        if QtWidgets.QMessageBox.question(self, "Confirma", "Apagar tudo?", QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No) == QtWidgets.QMessageBox.Yes:
            con = sqlite3.connect(DB_PATH)
            con.execute("DELETE FROM historico WHERE usuario_id=?", (usuario_logado["id"],))
            con.commit(); con.close()
            self.carregar_tabela()

    def voltar_energia(self):
        global tela_ativa
        tela_ativa = TelaEnergia()
        tela_ativa.show()
        self.close()

    def abrir_dashboard(self):
        global tela_ativa
        tela_ativa = TelaDashboard()
        tela_ativa.show()
        self.close()

class TelaEnergia(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.join(BASE_DIR, "telas", "energia.ui"), self)
        self.showMaximized()
        
        self.linha_consumo_kwh.setReadOnly(True)
        
        self.btn_calcular.clicked.connect(self.calcular)
        self.btn_salvar.clicked.connect(self.salvar_historico)
        self.btn_historico.clicked.connect(self.abrir_historico)
        self.btn_dashboard.clicked.connect(self.abrir_dashboard)
        
        self.timer_usb = QTimer()
        self.timer_usb.timeout.connect(self.verificar_usb)
        self.timer_usb.start(100)
        
        self._resultado = None

    def verificar_usb(self):
        if not (esp32 and esp32.in_waiting > 0): return
        try:
            linha = esp32.readline().decode('utf-8', errors='ignore').strip()
            if not linha: return
            
            partes = linha.split(',')
            cmd = partes[0].upper()

            if cmd == "LIGAR" and len(partes) >= 3:
                self.linha_aparelho.setText(partes[1].strip())
                self.linha_potencia.setText(partes[2].strip())
                self.linha_tempo.setText("Contando...") 

            elif cmd == "DESLIGAR" and len(partes) >= 4:
                self.linha_aparelho.setText(partes[1].strip())
                self.linha_potencia.setText(partes[3].strip())
                
                tempo_segundos = float(partes[2].strip())
                minutos_limpos = round(tempo_segundos / 60, 2) 
                self.linha_tempo.setText(str(minutos_limpos))
                
                self.calcular() 
        except: pass

    def calcular(self):
        try:
            aparelho = self.linha_aparelho.text().strip() or "Aparelho"
            potencia = float(self.linha_potencia.text().replace(',', '.'))
            
            txt_tempo = self.linha_tempo.text()
            if txt_tempo == "Contando..." or not txt_tempo: return
            
            minutos = float(txt_tempo.replace(',', '.'))
    
            consumo_kwh = (potencia * minutos) / 60000
            self.linha_consumo_kwh.setText(f"{consumo_kwh:.4f}")
            
            custo = consumo_kwh * 1.2
            self.label_resultado.setText(f"R$ {custo:.2f}")

            self._resultado = {
                "aparelho": aparelho, "potencia": potencia, 
                "tempo": minutos, "consumo_kwh": consumo_kwh, "custo": custo
            }
        except:
            self.linha_consumo_kwh.setText("0.0000")
            self.label_resultado.setText("R$ 0,00")

    def salvar_historico(self):
        if not self._resultado: return
        r = self._resultado
        con = sqlite3.connect(DB_PATH)
        con.execute("INSERT INTO historico (usuario_id, aparelho, potencia, tempo, consumo_kwh, custo_reais) VALUES (?,?,?,?,?,?)",
                    (usuario_logado["id"], r["aparelho"], r["potencia"], r["tempo"], r["consumo_kwh"], r["custo"]))
        con.commit(); con.close()
        QtWidgets.QMessageBox.information(self, "Sucesso", "Salvo!")

    def abrir_historico(self):
        global tela_ativa
        tela_ativa = TelaHistorico()
        tela_active_show = tela_ativa.show()
        self.close()

    def abrir_dashboard(self):
        global tela_ativa
        tela_ativa = TelaDashboard()
        tela_ativa.show()
        self.close()

class TelaLogin(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.join(BASE_DIR, "telas", "page - login.ui"), self)
        self.showMaximized()
        
        self.btn_entrar.clicked.connect(self.tentar_login)
        self.btn_cadastrar.clicked.connect(self.ir_cadastro)
        
        # --- MODIFICAÇÃO: Faz o botão Enter nos inputs de texto acionar o login ---
        self.linha_usuario.returnPressed.connect(self.tentar_login)
        self.linha_senha.returnPressed.connect(self.tentar_login)
        
        if hasattr(self, 'btn_esqueci'):
            self.btn_esqueci.clicked.connect(self.esqueci_senha)

    def tentar_login(self):
        email = self.linha_usuario.text()
        senha = self.linha_senha.text()
        
        if not email or not senha:
            QtWidgets.QMessageBox.warning(self, "Aviso", "Preencha todos os campos.")
            return

        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id, nome FROM usuarios WHERE email=? AND senha=?", (email, senha))
        user = cur.fetchone()
        con.close()
        
        if user:
            usuario_logado["id"], usuario_logado["nome"] = user[0], user[1]
            
            global tela_ativa
            tela_ativa = TelaEnergia()
            tela_ativa.show()
            self.close() 
        else:
            QtWidgets.QMessageBox.warning(self, "Erro", "Login incorreto!")

    def ir_cadastro(self):
        global tela_ativa
        tela_ativa = TelaCadastro()
        tela_ativa.show()
        self.close() 

    def esqueci_senha(self):
        QtWidgets.QMessageBox.information(self, "Recuperação", "Link de recuperação enviado para seu e-mail.")

class TelaCadastro(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.join(BASE_DIR, "telas", "cadastro.ui"), self)
        self.showMaximized()
        self.btn_criarc.clicked.connect(self.salvar)
        self.btn_voltar.clicked.connect(self.voltar)

    def salvar(self):
        nome, email, senha, confirma = self.linha_nome.text(), self.linha_email.text(), self.linha_senha.text(), self.linha_confirm.text()
        if not nome or not email or senha != confirma:
            QtWidgets.QMessageBox.warning(self, "Erro", "Dados inválidos!")
            return
        try:
            con = sqlite3.connect(DB_PATH)
            con.execute("INSERT INTO usuarios (nome, email, senha) VALUES (?,?,?)", (nome, email, senha))
            con.commit(); con.close()
            
            global tela_ativa
            tela_ativa = TelaLogin()
            tela_ativa.show()
            self.close()
        except:
            QtWidgets.QMessageBox.warning(self, "Erro", "Erro ao cadastrar.")
    
    def voltar(self):
        global tela_ativa
        tela_ativa = TelaLogin()
        tela_ativa.show()
        self.close() 

if __name__ == "__main__":
    iniciar_banco()
    app = QtWidgets.QApplication(sys.argv)
    
    tela_ativa = TelaLogin()
    tela_ativa.show()
    
    sys.exit(app.exec_())