import ctypes
import json
import os
import random
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox
from urllib.request import Request, urlopen

from PIL import Image, ImageColor, ImageTk
import pygame
from temas import GerenciadorTemas

try:
    from tkinterdnd2 import TkinterDnD
except ImportError:
    TkinterDnD = None

# ============================================================
# Desemprego Bot — os PNGs controlam o visual dos botões
# ============================================================

def obter_pasta_programa():
    """Encontra recursos tanto no projeto quanto no _internal do PyInstaller 6."""
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent

    pasta_exe = Path(sys.executable).resolve().parent
    candidatos = [
        pasta_exe,
        pasta_exe / "_internal",
        Path(getattr(sys, "_MEIPASS", pasta_exe)),
    ]
    for candidato in candidatos:
        if (candidato / "programa_image").is_dir() or (candidato / "audios").is_dir():
            return candidato
    return pasta_exe


CAMINHO_BASE = obter_pasta_programa()
PASTA_INSTALACAO = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else CAMINHO_BASE
)
PASTA_CONFIG = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "DesempregoBot"
CAMINHO_CONFIG = PASTA_CONFIG / "config.json"
PASTA_AUDIOS = CAMINHO_BASE / "audios"
PASTA_RECURSOS = CAMINHO_BASE / "programa_image"
CAMINHO_IMAGEM_POPUP = CAMINHO_BASE / "imagem.png"
CAMINHO_FUNDO = PASTA_RECURSOS / "Fundo.png"
CAMINHO_LOGO = PASTA_RECURSOS / "logo.png"
CAMINHO_BOTAO1 = PASTA_RECURSOS / "botao1.png"
CAMINHO_BOTAO2 = PASTA_RECURSOS / "botao2.png"
CAMINHO_ICONE = PASTA_RECURSOS / "icon.ico"
CAMINHO_CONFIG_ICON = PASTA_RECURSOS / "config.png"
CAMINHO_CUSTOM_ICON = PASTA_RECURSOS / "custom.png"
CAMINHO_NOTHEME = PASTA_RECURSOS / "notheme.png"
CAMINHO_IMAGEM_POPUP_ATIVO = CAMINHO_IMAGEM_POPUP

LARGURA_JANELA = 466
# Área de conteúdo mais compacta; a barra de título do Windows fica fora dela.
ALTURA_JANELA = 430
LARGURA_POPUP = 160
ALTURA_POPUP = 160

# Lavanda claro combina com o fundo e fica mais confortável que preto puro.
COR_TEXTO = "#f4e7ff"
COR_TEXTO_SECUNDARIO = "#e3cdfb"
COR_BRANCO = "#fffaff"
FONTE_PRINCIPAL = "Trebuchet MS"
VERSAO_ATUAL = "1.0.4"
REPOSITORIO_GITHUB = "MentalGlitch/desemprego-bot"
VOLUME_CLICK = 0.45
TEMPO_PADRAO = "10"
CONFIG_PADRAO = {
    "config_versao": 2,
    "volume": 1.0,
    "sons_interface": True,
    "evitar_repeticao": False,
    "guardar_ultimo_tempo": False,
    "ultimo_tempo": TEMPO_PADRAO,
}


def carregar_configuracoes():
    try:
        with CAMINHO_CONFIG.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
            if not isinstance(dados, dict) or dados.get("config_versao") != CONFIG_PADRAO["config_versao"]:
                return CONFIG_PADRAO.copy()
            configuracoes = CONFIG_PADRAO.copy()
            configuracoes.update(dados if isinstance(dados, dict) else {})
            configuracoes["volume"] = max(0.0, min(1.0, float(configuracoes["volume"])))
            return configuracoes
    except (OSError, ValueError, TypeError):
        return CONFIG_PADRAO.copy()


CONFIGURACOES = carregar_configuracoes()


def salvar_configuracoes():
    try:
        PASTA_CONFIG.mkdir(parents=True, exist_ok=True)
        with CAMINHO_CONFIG.open("w", encoding="utf-8") as arquivo:
            json.dump(CONFIGURACOES, arquivo, ensure_ascii=False, indent=2)
    except OSError as erro:
        print(f"Aviso: não foi possível salvar as configurações: {erro}")

pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
try:
    pygame.mixer.init()
except pygame.error as erro:
    print(f"Aviso: não foi possível iniciar o áudio: {erro}")

sons = list(PASTA_AUDIOS.glob("*.wav")) + list(PASTA_AUDIOS.glob("*.mp3"))
audios_carregados = {}
duracoes_audios = {}


def carregar_lista_audios(lista):
    """Troca a biblioteca de alarmes sem misturar arquivos de temas."""
    global audios_carregados, duracoes_audios
    novos = {}
    duracoes = {}
    for som_path in lista:
        try:
            som_path = Path(som_path)
            if not som_path.exists():
                continue
            som = pygame.mixer.Sound(str(som_path))
            novos[som_path] = som
            duracoes[som_path] = som.get_length()
        except Exception as erro:
            print(f"Erro ao carregar {som_path}: {erro}")
    audios_carregados = novos
    duracoes_audios = duracoes
    return len(novos)


carregar_lista_audios(sons)


def carregar_som_interface(nome):
    for pasta in (PASTA_RECURSOS, PASTA_AUDIOS):
        caminho = pasta / nome
        if caminho.exists():
            try:
                return pygame.mixer.Sound(str(caminho))
            except Exception as erro:
                print(f"Aviso: não foi possível carregar {caminho}: {erro}")
    print(f"Aviso: som de interface {nome} não encontrado")
    return None


som_click = carregar_som_interface("Click.mp3")


def tocar_click():
    if som_click and CONFIGURACOES.get("sons_interface", True):
        try:
            som_click.set_volume(float(CONFIGURACOES.get("volume", VOLUME_CLICK)))
            som_click.play()
        except pygame.error as erro:
            print(f"Aviso: não foi possível tocar Click.mp3: {erro}")


def converter_entrada_para_segundos(entrada):
    """Aceita segundos (10) ou minutos:segundos (1:00)."""
    entrada = entrada.strip()
    if not entrada:
        return None
    try:
        if ":" in entrada:
            partes = entrada.split(":")
            if len(partes) != 2:
                return None
            minutos, segundos = (int(parte.strip()) for parte in partes)
            if minutos < 0 or segundos < 0 or segundos >= 60:
                return None
            total = minutos * 60 + segundos
            return total if total > 0 else None
        valor = int(entrada)
        return valor if valor > 0 else None
    except (TypeError, ValueError):
        return None


def redimensionar_preenchendo(imagem, tamanho):
    """Preenche o espaço sem deformar a imagem e sem aplicar efeitos nela."""
    largura, altura = tamanho
    imagem = imagem.convert("RGBA")
    escala = max(largura / imagem.width, altura / imagem.height)
    novo_tamanho = (max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala)))
    imagem = imagem.resize(novo_tamanho, Image.Resampling.LANCZOS)
    esquerda = (imagem.width - largura) // 2
    topo = (imagem.height - altura) // 2
    return imagem.crop((esquerda, topo, esquerda + largura, topo + altura))


def carregar_imagem(caminho, tamanho, fallback="#7625d2"):
    try:
        return redimensionar_preenchendo(Image.open(caminho), tamanho)
    except Exception as erro:
        print(f"Aviso: não foi possível carregar {caminho.name}: {erro}")
        return Image.new("RGBA", tamanho, fallback)


def carregar_png_interface(caminho, fallback_tamanho):
    """Carrega o PNG sem transformar o design; só usa fallback se ele não existir."""
    try:
        imagem = Image.open(caminho).convert("RGBA")
        return imagem, ImageTk.PhotoImage(imagem)
    except Exception as erro:
        print(f"Aviso: {caminho.name} não encontrado: {erro}")
        imagem = Image.new("RGBA", fallback_tamanho, (116, 37, 210, 255))
        return imagem, ImageTk.PhotoImage(imagem)


def mostrar_popup_perfeito(duracao_ms, som_obj, ao_terminar=None):
    popup = tk.Toplevel()
    popup.overrideredirect(True)
    popup.attributes("-topmost", True)
    popup.configure(bg="#000000")
    popup.wm_attributes("-transparentcolor", "#000000")

    tela_largura = popup.winfo_screenwidth()
    tela_altura = popup.winfo_screenheight()
    pos_x = tela_largura - LARGURA_POPUP - 28
    pos_y_final = tela_altura - ALTURA_POPUP - 28
    pos_y_inicial = tela_altura + 20
    pos_y_atual = float(pos_y_inicial)
    popup.geometry(f"{LARGURA_POPUP}x{ALTURA_POPUP}+{pos_x}+{int(pos_y_atual)}")

    canvas = tk.Canvas(popup, width=LARGURA_POPUP, height=ALTURA_POPUP,
                       bg="#000000", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    # Popup intencionalmente minimalista: somente a imagem, inteira e sem texto.
    try:
        imagem_popup = Image.open(CAMINHO_IMAGEM_POPUP_ATIVO).convert("RGBA")
        imagem_popup.thumbnail((LARGURA_POPUP, ALTURA_POPUP), Image.Resampling.LANCZOS)
    except Exception as erro:
        print(f"Aviso: não foi possível carregar a imagem do popup: {erro}")
        imagem_popup = Image.new("RGBA", (LARGURA_POPUP, ALTURA_POPUP), "#7625d2")
    imagem_tk = ImageTk.PhotoImage(imagem_popup)
    canvas.create_image(LARGURA_POPUP // 2, ALTURA_POPUP // 2,
                        image=imagem_tk, anchor="center")
    canvas.image = imagem_tk

    try:
        som_obj.set_volume(float(CONFIGURACOES.get("volume", VOLUME_CLICK)))
        canal = som_obj.play()
    except pygame.error:
        canal = None

    estado = "subindo"
    timer_saida_id = None
    termino_notificado = False

    def notificar_termino():
        nonlocal termino_notificado
        if not termino_notificado:
            termino_notificado = True
            if ao_terminar:
                ao_terminar()

    def fechar(_event=None):
        nonlocal estado
        if estado != "descendendo":
            if canal:
                canal.stop()
            if timer_saida_id:
                popup.after_cancel(timer_saida_id)
            estado = "descendendo"
            animar()

    def animar():
        nonlocal pos_y_atual, estado, timer_saida_id
        try:
            hwnd = ctypes.windll.user32.GetParent(popup.winfo_id())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
        except (AttributeError, OSError):
            pass
        if estado == "subindo":
            distancia = pos_y_final - pos_y_atual
            if abs(distancia) > 0.6:
                pos_y_atual += distancia * 0.16
                popup.geometry(f"{LARGURA_POPUP}x{ALTURA_POPUP}+{pos_x}+{int(pos_y_atual)}")
                popup.after(16, animar)
            else:
                pos_y_atual = pos_y_final
                estado = "parado"
                timer_saida_id = popup.after(duracao_ms, iniciar_saida)
        elif estado == "parado":
            popup.after(100, animar)
        else:
            distancia = pos_y_inicial - pos_y_atual
            if abs(distancia) > 0.6:
                pos_y_atual += distancia * 0.13
                popup.geometry(f"{LARGURA_POPUP}x{ALTURA_POPUP}+{pos_x}+{int(pos_y_atual)}")
                popup.after(16, animar)
            else:
                if canal:
                    canal.stop()
                notificar_termino()
                popup.destroy()

    def iniciar_saida():
        nonlocal estado
        if estado in ("subindo", "parado"):
            estado = "descendendo"
            animar()

    popup.bind("<Double-Button-1>", fechar)
    canvas.bind("<Double-Button-1>", fechar)
    popup.after(10, animar)


def versao_numerica(valor):
    try:
        return tuple(int(parte) for parte in valor.lstrip("vV").split(".")[:3])
    except (AttributeError, TypeError, ValueError):
        return (0, 0, 0)


def verificar_atualizacao(root):
    """Consulta a Release pública sem travar a interface principal."""
    def consultar():
        try:
            url_api = f"https://api.github.com/repos/{REPOSITORIO_GITHUB}/releases/latest"
            requisicao = Request(url_api, headers={"User-Agent": "Desemprego-Bot"})
            with urlopen(requisicao, timeout=8) as resposta:
                release = json.loads(resposta.read().decode("utf-8"))

            versao_nova = release.get("tag_name", "")
            if versao_numerica(versao_nova) <= versao_numerica(VERSAO_ATUAL):
                return

            assets = release.get("assets", [])
            asset_zip = next(
                (asset for asset in assets if asset.get("name", "").lower().endswith(".zip")),
                None,
            )
            if not asset_zip:
                return

            root.after(0, lambda: oferecer_atualizacao(
                root, versao_nova, asset_zip["browser_download_url"]
            ))
        except Exception as erro:
            print(f"Verificação de atualização ignorada: {erro}")

    threading.Thread(target=consultar, daemon=True).start()


def oferecer_atualizacao(root, versao_nova, url_download):
    resposta = messagebox.askyesno(
        "Atualização disponível",
        f"A versão {versao_nova} do Desemprego Bot está disponível.\n\n"
        "Deseja baixar e instalar agora?",
        parent=root,
    )
    if not resposta:
        return

    atualizador = PASTA_INSTALACAO / "Atualizador.exe"
    executavel_atual = Path(sys.executable).resolve()
    if not atualizador.exists():
        messagebox.showwarning(
            "Atualizador ausente",
            "Esta instalação não contém o Atualizador.exe.\n"
            "Baixe a próxima versão completa pela Release.",
            parent=root,
        )
        return

    subprocess.Popen([
        str(atualizador),
        "--pid", str(os.getpid()),
        "--url", url_download,
        "--target", str(PASTA_INSTALACAO),
        "--restart", str(executavel_atual),
    ], cwd=str(PASTA_INSTALACAO))
    root.destroy()


class AppAlarme:
    def __init__(self, root):
        self.root = root
        self.CAMINHO_IMAGEM_POPUP = CAMINHO_IMAGEM_POPUP
        self.CAMINHO_NOTHEME = CAMINHO_NOTHEME
        self.temas = GerenciadorTemas(self, PASTA_CONFIG)
        self.root.title(f"Desemprego Bot v{VERSAO_ATUAL}")
        self.root.geometry(f"{LARGURA_JANELA}x{ALTURA_JANELA}")
        self.root.resizable(False, False)
        self.contagem_id = None
        self.alarme_ativo = False
        self.ultimo_audio = None
        self.historico_audios = []
        self.ultimo_tempo = str(CONFIGURACOES.get("ultimo_tempo", TEMPO_PADRAO)) \
            if CONFIGURACOES.get("guardar_ultimo_tempo", False) else TEMPO_PADRAO
        self.root.protocol("WM_DELETE_WINDOW", self.fechar_app)

        # Abre sempre centralizado na tela, em vez de usar uma posição aleatória.
        self.root.update_idletasks()
        tela_largura = self.root.winfo_screenwidth()
        tela_altura = self.root.winfo_screenheight()
        pos_x = max(0, (tela_largura - LARGURA_JANELA) // 2)
        pos_y = max(0, (tela_altura - ALTURA_JANELA) // 2)
        self.root.geometry(f"{LARGURA_JANELA}x{ALTURA_JANELA}+{pos_x}+{pos_y}")

        try:
            # O mesmo ICO aparece na barra de título e na barra de tarefas.
            self.root.iconbitmap(default=str(CAMINHO_ICONE))
            # Também aplica o ícone via Tk para o teste executando diretamente o .py.
            self.icone_tk = ImageTk.PhotoImage(Image.open(CAMINHO_ICONE).convert("RGBA"))
            self.root.iconphoto(True, self.icone_tk)
        except Exception:
            pass

        # Fundo e logo permanecem como antes; a nova arte fica só nos dois controles.
        self.fundo_tk = ImageTk.PhotoImage(carregar_imagem(
            CAMINHO_FUNDO, (LARGURA_JANELA, ALTURA_JANELA)
        ))
        self.canvas = tk.Canvas(root, width=LARGURA_JANELA, height=ALTURA_JANELA,
                                bg="#7625d2", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.fundo_item = self.canvas.create_image(0, 0, image=self.fundo_tk, anchor="nw")

        try:
            self.config_original = Image.open(CAMINHO_CONFIG_ICON).convert("RGBA")
            imagem_config = self.config_original.copy()
            imagem_config.thumbnail((80, 80), Image.Resampling.LANCZOS)
            self.config_tk = ImageTk.PhotoImage(imagem_config)
            self.config_hover_after = None
            self.config_item = self.canvas.create_image(
                LARGURA_JANELA - 46, 42, image=self.config_tk, anchor="center",
                tags=("config_visual",)
            )
            self.canvas.tag_bind(self.config_item, "<Enter>", lambda _event: self.iniciar_hover_config())
            self.canvas.tag_bind(self.config_item, "<Leave>", lambda _event: self.finalizar_hover_config())
        except Exception as erro:
            print(f"Aviso: config.png não encontrada ou inválida: {erro}")
            self.config_tk = None
            self.config_original = None
            self.config_hover_after = None
            self.config_item = self.canvas.create_text(
                LARGURA_JANELA - 14, 14, text="⚙", anchor="ne",
                fill=COR_BRANCO, font=(FONTE_PRINCIPAL, 24, "normal")
            )
        self.canvas.tag_bind(self.config_item, "<Button-1>", lambda _event: self.abrir_configuracoes())

        self.temas_original = None
        self.temas_tk = None
        self.temas_item = None
        try:
            self.temas_original = Image.open(CAMINHO_CUSTOM_ICON).convert("RGBA")
            imagem_temas = self.temas_original.copy()
            imagem_temas.thumbnail((80, 80), Image.Resampling.LANCZOS)
            self.temas_tk = ImageTk.PhotoImage(imagem_temas)
            self.temas_item = self.canvas.create_image(
                46, 42, image=self.temas_tk, anchor="center", tags=("temas_visual",)
            )
            self.canvas.tag_bind(self.temas_item, "<Enter>", lambda _event: self.atualizar_hover_temas(True))
            self.canvas.tag_bind(self.temas_item, "<Leave>", lambda _event: self.atualizar_hover_temas(False))
        except Exception as erro:
            print(f"Aviso: custom.png não encontrada ou inválida: {erro}")
        if self.temas_item:
            self.canvas.tag_bind(self.temas_item, "<Button-1>", lambda _event: (tocar_click(), self.temas.abrir()))

        self.logo_tk = None
        try:
            logo = Image.open(CAMINHO_LOGO).convert("RGBA")
            logo.thumbnail((323, 96), Image.Resampling.LANCZOS)
            self.logo_tk = ImageTk.PhotoImage(logo)
            self.logo_item = self.canvas.create_image(LARGURA_JANELA // 2, 84, image=self.logo_tk, anchor="center")
            self.logo_is_image = True
        except Exception as erro:
            print(f"Aviso: logo.png não encontrada ou inválida: {erro}")
            self.logo_item = self.canvas.create_text(LARGURA_JANELA // 2, 84, text="DESEMPREGO BOT",
                                                     fill="#ffd82e", font=(FONTE_PRINCIPAL, 30, "normal"))
            self.logo_is_image = False

        # Fonte mais leve: normal, sem negrito grosso.
        self.titulo_status_item = self.canvas.create_text(
            LARGURA_JANELA // 2, 184, text="Tempo do alarme:",
            fill=COR_TEXTO, font=(FONTE_PRINCIPAL, 23, "normal")
        )

        # BOTAO 1: a imagem é o design; o texto digitável fica por cima dela.
        imagem1, self.botao1_tk = carregar_png_interface(CAMINHO_BOTAO1, (280, 48))
        self.botao1_original = imagem1
        self.botao1_base = imagem1.copy()
        self.botao1_largura = imagem1.width
        self.botao1_altura = imagem1.height
        self.botao1_x = (LARGURA_JANELA - self.botao1_largura) // 2
        self.botao1_y = 218
        self.botao1_item = self.canvas.create_image(
            self.botao1_x, self.botao1_y, image=self.botao1_tk, anchor="nw",
            tags=("botao1_visual",)
        )

        # Fundo aproximado apenas para o Entry nativo não criar um retângulo branco.
        cor_entry = self.cor_central(imagem1)
        self.entry_tempo = tk.Entry(
            root, font=(FONTE_PRINCIPAL, 16, "normal"), justify="center",
            bg=cor_entry, fg=COR_BRANCO, insertbackground=COR_BRANCO,
            disabledbackground=cor_entry, disabledforeground=COR_BRANCO,
            relief="flat", bd=0, highlightthickness=0
        )
        margem_x = max(18, round(self.botao1_largura * 0.10))
        self.entry_tempo.place(
            x=self.botao1_x + margem_x,
            y=self.botao1_y + max(4, self.botao1_altura // 5),
            width=max(80, self.botao1_largura - 2 * margem_x),
            height=max(28, round(self.botao1_altura * 0.58)),
        )
        self.entry_tempo.insert(0, self.ultimo_tempo)
        self.entry_tempo.bind("<Return>", lambda _event: self.iniciar_contagem())
        self.entry_tempo.bind("<Enter>", lambda _event: self.iniciar_hover_botao1())
        self.entry_tempo.bind("<Leave>", lambda _event: self.finalizar_hover_botao1())
        self.canvas.tag_bind(self.botao1_item, "<Enter>", lambda _event: self.iniciar_hover_botao1())
        self.canvas.tag_bind(self.botao1_item, "<Leave>", lambda _event: self.finalizar_hover_botao1())

        # BOTAO 2: imagem + texto sobreposto; ambos desaparecem durante a contagem.
        imagem2, self.botao2_tk = carregar_png_interface(CAMINHO_BOTAO2, (280, 48))
        self.botao2_original = imagem2
        self.botao2_base = imagem2.copy()
        self.botao2_largura = imagem2.width
        self.botao2_altura = imagem2.height
        self.botao2_x = (LARGURA_JANELA - self.botao2_largura) // 2
        self.botao2_y = 285
        self.botao2_item = self.canvas.create_image(
            self.botao2_x, self.botao2_y, image=self.botao2_tk, anchor="nw",
            tags=("botao2_visual",)
        )
        self.texto_tocar_item = self.canvas.create_text(
            LARGURA_JANELA // 2,
            self.botao2_y + self.botao2_altura / 2,
            text="Tocar",
            fill=COR_BRANCO,
            font=(FONTE_PRINCIPAL, 12, "normal"),
            tags=("botao2_visual",),
        )
        self.canvas.tag_bind(self.botao2_item, "<Button-1>", lambda _event: self.acionar_botao_alarme())
        self.canvas.tag_bind(self.texto_tocar_item, "<Button-1>", lambda _event: self.acionar_botao_alarme())
        self.canvas.tag_bind(self.botao2_item, "<Enter>", lambda _event: self.iniciar_hover_botao2())
        self.canvas.tag_bind(self.texto_tocar_item, "<Enter>", lambda _event: self.iniciar_hover_botao2())
        self.canvas.tag_bind(self.botao2_item, "<Leave>", lambda _event: self.finalizar_hover_botao2())
        self.canvas.tag_bind(self.texto_tocar_item, "<Leave>", lambda _event: self.finalizar_hover_botao2())

        self.exemplo_item = self.canvas.create_text(
            LARGURA_JANELA // 2, 389, text="Ex: 1 ou 1:00",
            fill=COR_TEXTO_SECUNDARIO, font=(FONTE_PRINCIPAL, 20, "normal")
        )

        self.hover_alvo = {"botao1": 1.0, "botao2": 1.0}
        self.hover_escala = {"botao1": 1.0, "botao2": 1.0}
        self.hover_after = {"botao1": None, "botao2": None}
        self.controles_visiveis = True
        self.manter_icones_no_topo()
        self.root.after(80, self.temas.aplicar_ativo)

    @staticmethod
    def cor_central(imagem):
        """Escolhe a cor média do centro para o Entry se misturar ao PNG."""
        try:
            x = imagem.width // 2
            y = imagem.height // 2
            r, g, b, _a = imagem.getpixel((x, y))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#8b4cde"

    def atualizar_hover_temas(self, ativo):
        if self.temas_original is None or self.temas_item is None:
            return
        limite = 98 if ativo else 80
        imagem = self.temas_original.copy()
        imagem.thumbnail((limite, limite), Image.Resampling.LANCZOS)
        self.temas_tk = ImageTk.PhotoImage(imagem)
        self.canvas.itemconfigure(self.temas_item, image=self.temas_tk)
        self.canvas.coords(self.temas_item, 46, 42)

    def manter_icones_no_topo(self):
        for item in (self.temas_item, self.config_item):
            if item:
                self.canvas.tag_raise(item)

    @staticmethod
    def tingir_botao(imagem, cor):
        """Aplica uma camada translúcida apenas nos pixels existentes do PNG."""
        if not cor:
            return imagem.copy()
        try:
            rgb = ImageColor.getrgb(cor)
            camada = Image.new("RGBA", imagem.size, (*rgb, 78))
            alpha = imagem.getchannel("A")
            camada.putalpha(alpha.point(lambda valor: round(valor * 0.30)))
            return Image.alpha_composite(imagem.convert("RGBA"), camada)
        except (ValueError, TypeError):
            return imagem.copy()

    def aplicar_tema(self, tema):
        """Aplica um tema sem reiniciar o temporizador nem alterar configurações gerais."""
        global CAMINHO_IMAGEM_POPUP_ATIVO
        tema_personalizado = bool(tema and tema.get("_id"))
        caminho_base = self.temas.pasta / tema["_id"] if tema_personalizado else None
        cor_tema = (tema.get("cor") or "#ffffff") if tema_personalizado else None
        caminho_fundo = (caminho_base / tema["background"] if caminho_base and tema.get("background")
                         else (caminho_base / "__sem_background__.png" if tema_personalizado else CAMINHO_FUNDO))
        caminho_logo = (caminho_base / tema["logo"] if caminho_base and tema.get("logo")
                        else (CAMINHO_NOTHEME if tema_personalizado else CAMINHO_LOGO))
        caminho_popup = (caminho_base / tema["popup"] if caminho_base and tema.get("popup")
                         else (CAMINHO_NOTHEME if tema_personalizado else CAMINHO_IMAGEM_POPUP))
        CAMINHO_IMAGEM_POPUP_ATIVO = caminho_popup if caminho_popup.exists() else CAMINHO_IMAGEM_POPUP

        self.botao1_original = self.tingir_botao(self.botao1_base, cor_tema)
        self.botao2_original = self.tingir_botao(self.botao2_base, cor_tema)
        self.aplicar_escala_hover("botao1", self.hover_escala["botao1"])
        self.aplicar_escala_hover("botao2", self.hover_escala["botao2"])
        cor_entry = self.cor_central(self.botao1_original)
        self.entry_tempo.configure(bg=cor_entry, disabledbackground=cor_entry)

        self.fundo_tk = ImageTk.PhotoImage(carregar_imagem(
            caminho_fundo, (LARGURA_JANELA, ALTURA_JANELA), cor_tema or "#7625d2"
        ))
        self.canvas.itemconfigure(self.fundo_item, image=self.fundo_tk)
        self.canvas.configure(bg=cor_tema or "#7625d2")
        self.manter_icones_no_topo()
        try:
            logo = Image.open(caminho_logo).convert("RGBA")
            logo.thumbnail((323, 96), Image.Resampling.LANCZOS)
            novo_logo = ImageTk.PhotoImage(logo)
            if not self.logo_is_image:
                self.canvas.delete(self.logo_item)
                self.logo_item = self.canvas.create_image(LARGURA_JANELA // 2, 84, image=novo_logo, anchor="center")
                self.logo_is_image = True
            else:
                self.canvas.itemconfigure(self.logo_item, image=novo_logo)
            self.logo_tk = novo_logo
        except Exception:
            pass
        self.manter_icones_no_topo()
        try:
            rgb = ImageColor.getrgb(cor_tema) if cor_tema else (118, 37, 210)
            texto_tema = "#35105f" if sum(rgb) / 3 > 190 else COR_TEXTO
        except ValueError:
            texto_tema = COR_TEXTO
        self.canvas.itemconfigure(self.titulo_status_item, fill=texto_tema)
        self.canvas.itemconfigure(self.exemplo_item, fill=texto_tema)
        caminhos_audio = []
        if caminho_base and tema.get("audios"):
            caminhos_audio = [caminho_base / nome for nome in tema["audios"]]
        if caminhos_audio and carregar_lista_audios(caminhos_audio) == 0:
            carregar_lista_audios(sons)
        elif not caminhos_audio:
            carregar_lista_audios(sons)
        self.historico_audios.clear()

    def atualizar_hover_config(self, escala):
        if self.config_original is None:
            return
        imagem = self.config_original.copy()
        tamanho = max(44, round(80 * escala))
        imagem.thumbnail((tamanho, tamanho), Image.Resampling.LANCZOS)
        self.config_tk = ImageTk.PhotoImage(imagem)
        self.canvas.itemconfigure(self.config_item, image=self.config_tk)
        self.canvas.coords(self.config_item, LARGURA_JANELA - 46, 42)
        self.config_hover_after = None

    def iniciar_hover_config(self):
        if self.config_original is not None:
            self.config_hover_after = self.root.after(1, lambda: self.atualizar_hover_config(1.22))

    def finalizar_hover_config(self):
        if self.config_original is not None:
            if self.config_hover_after:
                self.root.after_cancel(self.config_hover_after)
            self.config_hover_after = self.root.after(1, lambda: self.atualizar_hover_config(1.0))

    def atualizar_hover(self, nome):
        """Amplia a arte suavemente, preservando o centro e o texto alinhado."""
        alvo = self.hover_alvo[nome]
        atual = self.hover_escala[nome]
        diferenca = alvo - atual
        if abs(diferenca) < 0.002:
            self.hover_escala[nome] = alvo
            self.aplicar_escala_hover(nome, alvo)
            self.hover_after[nome] = None
            return
        nova_escala = atual + diferenca * 0.28
        self.hover_escala[nome] = nova_escala
        self.aplicar_escala_hover(nome, nova_escala)
        self.hover_after[nome] = self.root.after(16, lambda: self.atualizar_hover(nome))

    def aplicar_escala_hover(self, nome, escala):
        if nome == "botao1":
            original = self.botao1_original
            largura = max(1, round(original.width * escala))
            altura = max(1, round(original.height * escala))
            self.botao1_tk = ImageTk.PhotoImage(original.resize(
                (largura, altura), Image.Resampling.LANCZOS
            ))
            x = (LARGURA_JANELA - largura) // 2
            y = self.botao1_y + (self.botao1_altura - altura) // 2
            self.canvas.itemconfigure(self.botao1_item, image=self.botao1_tk)
            self.canvas.coords(self.botao1_item, x, y)
            margem_x = max(18, round(largura * 0.10))
            self.entry_tempo.place(
                x=x + margem_x, y=y + max(4, altura // 5),
                width=max(80, largura - 2 * margem_x),
                height=max(28, round(altura * 0.58)),
            )
            self.entry_tempo.config(font=(FONTE_PRINCIPAL, max(12, round(16 * escala)), "normal"))
        else:
            original = self.botao2_original
            largura = max(1, round(original.width * escala))
            altura = max(1, round(original.height * escala))
            self.botao2_tk = ImageTk.PhotoImage(original.resize(
                (largura, altura), Image.Resampling.LANCZOS
            ))
            x = (LARGURA_JANELA - largura) // 2
            y = self.botao2_y + (self.botao2_altura - altura) // 2
            self.canvas.itemconfigure(self.botao2_item, image=self.botao2_tk)
            self.canvas.coords(self.botao2_item, x, y)
            self.canvas.coords(self.texto_tocar_item,
                               LARGURA_JANELA // 2,
                               self.botao2_y + self.botao2_altura / 2)
            self.canvas.itemconfigure(self.texto_tocar_item,
                                      font=(FONTE_PRINCIPAL, max(12, round(12 * escala)), "normal"))

    def iniciar_hover_botao1(self):
        if self.controles_visiveis:
            self.hover_alvo["botao1"] = 1.03
            self.iniciar_animacao_hover("botao1")

    def finalizar_hover_botao1(self):
        self.hover_alvo["botao1"] = 1.0
        self.iniciar_animacao_hover("botao1")

    def iniciar_hover_botao2(self):
        if self.controles_visiveis:
            self.root.config(cursor="hand2")
            self.hover_alvo["botao2"] = 1.04
            self.iniciar_animacao_hover("botao2")

    def finalizar_hover_botao2(self):
        self.root.config(cursor="")
        self.hover_alvo["botao2"] = 1.0
        self.iniciar_animacao_hover("botao2")

    def iniciar_animacao_hover(self, nome):
        if self.hover_after[nome] is None:
            self.atualizar_hover(nome)

    def definir_visibilidade_botao2(self, visivel):
        estado = "normal" if visivel else "hidden"
        self.canvas.itemconfigure(self.botao2_item, state=estado)
        self.canvas.itemconfigure(self.texto_tocar_item, state=estado)

    def definir_visibilidade_botao1(self, visivel):
        estado = "normal" if visivel else "hidden"
        self.canvas.itemconfigure(self.botao1_item, state=estado)
        self.controles_visiveis = visivel
        if visivel:
            self.canvas.itemconfigure(self.titulo_status_item, text="Tempo do alarme:",
                                      font=(FONTE_PRINCIPAL, 23, "normal"))
            self.canvas.itemconfigure(self.exemplo_item, state="normal")
            self.aplicar_escala_hover("botao1", self.hover_escala["botao1"])
        else:
            self.canvas.itemconfigure(self.titulo_status_item, text="Áudio tocando")
            self.canvas.itemconfigure(self.exemplo_item, state="hidden")
            self.entry_tempo.place_forget()

    def restaurar_controles(self):
        self.alarme_ativo = False
        self.definir_visibilidade_botao1(True)
        self.entry_tempo.config(state="normal")
        self.definir_visibilidade_botao2(True)
        self.canvas.itemconfigure(self.texto_tocar_item, text="Tocar", fill=COR_BRANCO,
                                  font=(FONTE_PRINCIPAL, 12, "normal"))

    def fechar_app(self):
        valor = self.entry_tempo.get().strip()
        if CONFIGURACOES.get("guardar_ultimo_tempo", False) and valor and valor not in ("inválido", "sem áudio"):
            CONFIGURACOES["ultimo_tempo"] = valor
            salvar_configuracoes()
        self.root.destroy()

    def abrir_configuracoes(self):
        tocar_click()
        janela = tk.Toplevel(self.root)
        janela.title("Configurações")
        janela.geometry("330x350")
        janela.resizable(False, False)
        janela.transient(self.root)
        janela.grab_set()
        janela.update_idletasks()
        pos_x = self.root.winfo_rootx() + (self.root.winfo_width() - janela.winfo_width()) // 2
        pos_y = self.root.winfo_rooty() + (self.root.winfo_height() - janela.winfo_height()) // 2
        janela.geometry(f"+{pos_x}+{pos_y}")
        try:
            janela.attributes("-alpha", 0.97)
        except tk.TclError:
            pass

        fundo = "#35105f"
        janela.configure(bg=fundo)
        tk.Label(janela, text="Preferências", bg=fundo, fg=COR_BRANCO,
                 font=(FONTE_PRINCIPAL, 18, "normal")).pack(pady=(18, 8))

        volume_var = tk.DoubleVar(value=CONFIGURACOES.get("volume", 1.0) * 100)
        tk.Label(janela, text="Volume dos áudios", bg=fundo, fg=COR_TEXTO,
                 font=(FONTE_PRINCIPAL, 11, "normal")).pack()
        volume_label = tk.Label(janela, bg=fundo, fg=COR_TEXTO_SECUNDARIO,
                                font=(FONTE_PRINCIPAL, 9, "normal"))
        volume_label.pack()
        barra = tk.Canvas(janela, width=270, height=34, bg=fundo, highlightthickness=0)
        barra.pack(pady=(2, 8))
        inicio_barra, fim_barra = 18, 252
        barra.create_rectangle(inicio_barra, 11, fim_barra, 23, fill="#43176f", outline="")
        preenchimento = barra.create_rectangle(inicio_barra, 11, inicio_barra, 23,
                                               fill="#bd7cff", outline="")
        marcador = barra.create_oval(0, 5, 0, 29, fill="#f1d9ff", outline="#9b54e6", width=2)

        def atualizar_barra_volume(valor=None):
            percentual = max(0.0, min(100.0, float(volume_var.get() if valor is None else valor)))
            volume_var.set(percentual)
            x = inicio_barra + (fim_barra - inicio_barra) * percentual / 100
            barra.coords(preenchimento, inicio_barra, 11, max(inicio_barra, x), 23)
            barra.coords(marcador, x - 8, 5, x + 8, 29)
            volume_label.config(text=f"{round(percentual)}%")

        def arrastar_volume(event):
            percentual = (event.x - inicio_barra) / (fim_barra - inicio_barra) * 100
            atualizar_barra_volume(percentual)

        barra.bind("<Button-1>", arrastar_volume)
        barra.bind("<B1-Motion>", arrastar_volume)
        atualizar_barra_volume()

        interface_var = tk.BooleanVar(value=CONFIGURACOES.get("sons_interface", True))
        repetir_var = tk.BooleanVar(value=CONFIGURACOES.get("evitar_repeticao", False))
        guardar_var = tk.BooleanVar(value=CONFIGURACOES.get("guardar_ultimo_tempo", False))
        opcoes = (
            (interface_var, "Ativar sons dos botões"),
            (repetir_var, "Evitar repetir o último áudio"),
            (guardar_var, "Lembrar o último tempo usado"),
        )
        for variavel, texto in opcoes:
            tk.Checkbutton(janela, text=texto, variable=variavel, bg=fundo,
                           fg=COR_TEXTO, selectcolor="#5b2291", activebackground=fundo,
                           activeforeground=COR_BRANCO, font=(FONTE_PRINCIPAL, 10, "normal")
                           ).pack(anchor="w", padx=45, pady=3)

        tk.Button(janela, text="Sobre o programa", command=lambda: (janela.grab_release(), janela.destroy(), self.abrir_sobre()),
                  width=22, bg="#54207e", fg=COR_BRANCO, activebackground="#7737a6",
                  relief="flat", font=(FONTE_PRINCIPAL, 10, "normal")).pack(pady=(8, 3))

        botoes = tk.Frame(janela, bg=fundo)
        botoes.pack(pady=10)

        def salvar_e_fechar():
            CONFIGURACOES["volume"] = max(0.0, min(1.0, volume_var.get() / 100))
            CONFIGURACOES["sons_interface"] = interface_var.get()
            CONFIGURACOES["evitar_repeticao"] = repetir_var.get()
            CONFIGURACOES["guardar_ultimo_tempo"] = guardar_var.get()
            if guardar_var.get():
                valor_atual = self.entry_tempo.get().strip()
                if converter_entrada_para_segundos(valor_atual) is not None:
                    self.ultimo_tempo = valor_atual
                    CONFIGURACOES["ultimo_tempo"] = valor_atual
            else:
                self.ultimo_tempo = TEMPO_PADRAO
                CONFIGURACOES["ultimo_tempo"] = TEMPO_PADRAO
            salvar_configuracoes()
            janela.grab_release()
            janela.destroy()

        tk.Button(botoes, text="Salvar", command=salvar_e_fechar, width=10,
                  bg="#7e35d2", fg=COR_BRANCO, activebackground="#a25bea",
                  relief="flat", font=(FONTE_PRINCIPAL, 10, "normal")).pack(side="left", padx=5)
        tk.Button(botoes, text="Cancelar", command=janela.destroy, width=10,
                  bg="#54207e", fg=COR_BRANCO, activebackground="#7737a6",
                  relief="flat", font=(FONTE_PRINCIPAL, 10, "normal")).pack(side="left", padx=5)
        janela.protocol("WM_DELETE_WINDOW", janela.destroy)

    def abrir_sobre(self):
        janela = tk.Toplevel(self.root)
        janela.title("Sobre o Desemprego Bot")
        janela.geometry("410x430")
        janela.resizable(False, False)
        janela.transient(self.root)
        janela.grab_set()
        janela.update_idletasks()
        pos_x = self.root.winfo_rootx() + (self.root.winfo_width() - janela.winfo_width()) // 2
        pos_y = self.root.winfo_rooty() + (self.root.winfo_height() - janela.winfo_height()) // 2
        janela.geometry(f"+{pos_x}+{pos_y}")
        fundo = "#35105f"
        janela.configure(bg=fundo)
        janela.protocol("WM_DELETE_WINDOW", lambda: (janela.grab_release(), janela.destroy()))

        try:
            foto = Image.open(CAMINHO_IMAGEM_POPUP).convert("RGBA").copy()
            foto.thumbnail((145, 145), Image.Resampling.LANCZOS)
            foto_tk = ImageTk.PhotoImage(foto)
            tk.Label(janela, image=foto_tk, bg=fundo).pack(pady=(12, 5))
            janela.foto_sobre = foto_tk
        except Exception:
            pass

        tk.Label(janela, text="Desemprego Bot", bg=fundo, fg=COR_BRANCO,
                 font=(FONTE_PRINCIPAL, 18, "normal")).pack()
        tk.Label(janela, text=f"Versão {VERSAO_ATUAL}", bg=fundo, fg=COR_TEXTO_SECUNDARIO,
                 font=(FONTE_PRINCIPAL, 10, "normal")).pack(pady=(1, 7))
        texto = (
            "Alarme personalizável para tocar seus próprios áudios.\n"
            "Escolha o tempo e aguarde a reprodução.\n\n"
            "Criadora: Soryu"
        )
        tk.Label(janela, text=texto, justify="center", wraplength=330, bg=fundo,
                 fg=COR_TEXTO, font=(FONTE_PRINCIPAL, 10, "normal")).pack(pady=3)
        github = tk.Label(janela, text="GitHub: MentalGlitch/desemprego-bot",
                          bg=fundo, fg="#d4a9ff", cursor="hand2",
                          font=(FONTE_PRINCIPAL, 10, "underline"))
        github.pack(pady=(3, 6))
        github.bind("<Button-1>", lambda _event: webbrowser.open(
            "https://github.com/MentalGlitch/desemprego-bot"
        ))

        rodape = tk.Frame(janela, bg=fundo)
        rodape.pack(side="bottom", fill="x", padx=18, pady=12)
        tk.Button(rodape, text="Fechar", command=lambda: (janela.grab_release(), janela.destroy()),
                  width=12, bg="#54207e", fg=COR_BRANCO, activebackground="#7737a6",
                  relief="flat", font=(FONTE_PRINCIPAL, 10, "normal")).pack(side="left")
        tk.Button(rodape, text="Verificar versão", width=18,
                  command=lambda: self.verificar_atualizacao_manual(janela),
                  bg="#7e35d2", fg=COR_BRANCO, activebackground="#a25bea",
                  relief="flat", font=(FONTE_PRINCIPAL, 10, "normal")).pack(side="right")

    def verificar_atualizacao_manual(self, parent):
        tocar_click()

        def consultar():
            try:
                url_api = f"https://api.github.com/repos/{REPOSITORIO_GITHUB}/releases/latest"
                requisicao = Request(url_api, headers={"User-Agent": "Desemprego-Bot"})
                with urlopen(requisicao, timeout=8) as resposta:
                    release = json.loads(resposta.read().decode("utf-8"))
                versao_nova = release.get("tag_name", "")
                if versao_numerica(versao_nova) > versao_numerica(VERSAO_ATUAL):
                    asset = next((item for item in release.get("assets", [])
                                  if item.get("name", "").lower().endswith(".zip")), None)
                    if asset:
                        parent.after(0, lambda: oferecer_atualizacao(
                            self.root, versao_nova, asset["browser_download_url"]
                        ))
                        return
                parent.after(0, lambda: messagebox.showinfo(
                    "Atualizações", f"Você já está usando a versão mais recente: {VERSAO_ATUAL}.",
                    parent=parent
                ))
            except Exception as erro:
                parent.after(0, lambda: messagebox.showwarning(
                    "Atualizações", "Não foi possível verificar agora. Tente novamente mais tarde.",
                    parent=parent
                ))
                print(f"Verificação manual ignorada: {erro}")

        threading.Thread(target=consultar, daemon=True).start()

    def acionar_botao_alarme(self):
        if self.alarme_ativo:
            self.cancelar_alarme()
        else:
            self.iniciar_contagem()

    def cancelar_alarme(self):
        tocar_click()
        if self.contagem_id is not None:
            try:
                self.root.after_cancel(self.contagem_id)
            except tk.TclError:
                pass
            self.contagem_id = None
        self.alarme_ativo = False
        self.entry_tempo.config(state="normal")
        self.entry_tempo.delete(0, tk.END)
        self.ultimo_tempo = self.tempo_para_restaurar()
        self.entry_tempo.insert(0, self.ultimo_tempo)
        self.canvas.itemconfigure(self.texto_tocar_item, text="Tocar", fill=COR_BRANCO,
                                  font=(FONTE_PRINCIPAL, 12, "normal"))
        self.restaurar_controles()

    def tempo_para_restaurar(self):
        if CONFIGURACOES.get("guardar_ultimo_tempo", False):
            return self.ultimo_tempo
        return TEMPO_PADRAO

    def iniciar_contagem(self):
        if self.alarme_ativo:
            return
        if not audios_carregados:
            self.entry_tempo.delete(0, tk.END)
            self.entry_tempo.insert(0, "sem áudio")
            return

        # O clique acontece somente ao iniciar uma nova contagem.
        # Durante a contagem e durante a reprodução os controles ficam ocultos.
        tocar_click()

        segundos = converter_entrada_para_segundos(self.entry_tempo.get())
        if segundos is None:
            self.entry_tempo.delete(0, tk.END)
            self.entry_tempo.insert(0, "inválido")
            return

        self.ultimo_tempo = self.entry_tempo.get().strip()
        self.alarme_ativo = True
        if CONFIGURACOES.get("guardar_ultimo_tempo", False):
            CONFIGURACOES["ultimo_tempo"] = self.ultimo_tempo
            salvar_configuracoes()
        self.canvas.itemconfigure(
            self.titulo_status_item,
            text="Alarme ativo",
            font=(FONTE_PRINCIPAL, 18, "normal")
        )
        self.canvas.itemconfigure(
            self.texto_tocar_item,
            text="CANCELAR ALARME",
            fill="#ffe66d",
            font=(FONTE_PRINCIPAL, 13, "bold")
        )
        self.definir_visibilidade_botao2(True)
        self.entry_tempo.config(state="normal")
        self.contagem_regressiva(segundos)

    def contagem_regressiva(self, restante):
        if restante > 0:
            minutos, segundos = divmod(restante, 60)
            texto = f"{minutos}:{segundos:02d}" if minutos else str(segundos)
            # Entry desabilitado não aceita delete/insert no Tkinter.
            # Atualizamos primeiro e só depois bloqueamos a edição manual.
            self.entry_tempo.config(state="normal")
            self.entry_tempo.delete(0, tk.END)
            self.entry_tempo.insert(0, texto)
            self.entry_tempo.config(state="disabled")
            self.contagem_id = self.root.after(1000, lambda: self.contagem_regressiva(restante - 1))
            return

        opcoes_audio = list(audios_carregados.keys())
        if CONFIGURACOES.get("evitar_repeticao", False) and len(opcoes_audio) > 1:
            opcoes_audio = [audio for audio in opcoes_audio if audio not in self.historico_audios]
            if not opcoes_audio:
                self.historico_audios.clear()
                opcoes_audio = list(audios_carregados.keys())
        som_path = random.choice(opcoes_audio)
        self.ultimo_audio = som_path
        if CONFIGURACOES.get("evitar_repeticao", False):
            self.historico_audios.append(som_path)
            limite_historico = max(1, len(audios_carregados) - 1)
            self.historico_audios = self.historico_audios[-limite_historico:]
        som_obj = audios_carregados[som_path]
        duracao_ms = max(1000, int(duracoes_audios[som_path] * 1000))
        self.entry_tempo.config(state="normal")
        self.entry_tempo.delete(0, tk.END)
        self.ultimo_tempo = self.tempo_para_restaurar()
        self.entry_tempo.insert(0, self.ultimo_tempo)
        # Os dois controles ficam fora da tela durante todo o áudio.
        self.definir_visibilidade_botao2(False)
        self.definir_visibilidade_botao1(False)
        mostrar_popup_perfeito(duracao_ms, som_obj, self.restaurar_controles)


if __name__ == "__main__":
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    app = AppAlarme(root)
    # A consulta roda em segundo plano e não impede o programa de abrir.
    root.after(1500, lambda: verificar_atualizacao(root))
    root.mainloop()
