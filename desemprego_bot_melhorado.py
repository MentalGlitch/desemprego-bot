import ctypes
import json
import os
import random
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from urllib.request import Request, urlopen

from PIL import Image, ImageTk
import pygame

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
VERSAO_ATUAL = "1.0.2"
REPOSITORIO_GITHUB = "MentalGlitch/desemprego-bot"
VOLUME_CLICK = 0.45


def carregar_ultimo_tempo():
    try:
        with CAMINHO_CONFIG.open("r", encoding="utf-8") as arquivo:
            valor = json.load(arquivo).get("ultimo_tempo", "10")
            return str(valor) if valor else "10"
    except (OSError, ValueError, TypeError):
        return "10"


def salvar_ultimo_tempo(valor):
    try:
        PASTA_CONFIG.mkdir(parents=True, exist_ok=True)
        with CAMINHO_CONFIG.open("w", encoding="utf-8") as arquivo:
            json.dump({"ultimo_tempo": str(valor)}, arquivo, ensure_ascii=False, indent=2)
    except OSError as erro:
        print(f"Aviso: não foi possível salvar o último tempo: {erro}")

pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
try:
    pygame.mixer.init()
except pygame.error as erro:
    print(f"Aviso: não foi possível iniciar o áudio: {erro}")

sons = list(PASTA_AUDIOS.glob("*.wav")) + list(PASTA_AUDIOS.glob("*.mp3"))
audios_carregados = {}
duracoes_audios = {}
for som_path in sons:
    try:
        som = pygame.mixer.Sound(str(som_path))
        audios_carregados[som_path] = som
        duracoes_audios[som_path] = som.get_length()
    except Exception as erro:
        print(f"Erro ao carregar {som_path.name}: {erro}")


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
    if som_click:
        try:
            som_click.set_volume(VOLUME_CLICK)
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
        imagem_popup = Image.open(CAMINHO_IMAGEM_POPUP).convert("RGBA")
        imagem_popup.thumbnail((LARGURA_POPUP, ALTURA_POPUP), Image.Resampling.LANCZOS)
    except Exception as erro:
        print(f"Aviso: não foi possível carregar a imagem do popup: {erro}")
        imagem_popup = Image.new("RGBA", (LARGURA_POPUP, ALTURA_POPUP), "#7625d2")
    imagem_tk = ImageTk.PhotoImage(imagem_popup)
    canvas.create_image(LARGURA_POPUP // 2, ALTURA_POPUP // 2,
                        image=imagem_tk, anchor="center")
    canvas.image = imagem_tk

    try:
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
        self.root.title(f"Desemprego Bot v{VERSAO_ATUAL}")
        self.root.geometry(f"{LARGURA_JANELA}x{ALTURA_JANELA}")
        self.root.resizable(False, False)
        self.contagem_id = None
        self.ultimo_tempo = carregar_ultimo_tempo()
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
        self.canvas.create_image(0, 0, image=self.fundo_tk, anchor="nw")

        self.logo_tk = None
        try:
            logo = Image.open(CAMINHO_LOGO).convert("RGBA")
            logo.thumbnail((400, 128), Image.Resampling.LANCZOS)
            self.logo_tk = ImageTk.PhotoImage(logo)
            self.canvas.create_image(LARGURA_JANELA // 2, 84, image=self.logo_tk, anchor="center")
        except Exception as erro:
            print(f"Aviso: logo.png não encontrada ou inválida: {erro}")
            self.canvas.create_text(LARGURA_JANELA // 2, 84, text="DESEMPREGO BOT",
                                    fill="#ffd82e", font=(FONTE_PRINCIPAL, 30, "normal"))

        # Fonte mais leve: normal, sem negrito grosso.
        self.titulo_status_item = self.canvas.create_text(
            LARGURA_JANELA // 2, 184, text="Tempo do alarme:",
            fill=COR_TEXTO, font=(FONTE_PRINCIPAL, 23, "normal")
        )

        # BOTAO 1: a imagem é o design; o texto digitável fica por cima dela.
        imagem1, self.botao1_tk = carregar_png_interface(CAMINHO_BOTAO1, (280, 48))
        self.botao1_original = imagem1
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
        self.canvas.tag_bind(self.botao2_item, "<Button-1>", lambda _event: self.iniciar_contagem())
        self.canvas.tag_bind(self.texto_tocar_item, "<Button-1>", lambda _event: self.iniciar_contagem())
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
            self.canvas.itemconfigure(self.titulo_status_item, text="Tempo do alarme:")
            self.canvas.itemconfigure(self.exemplo_item, state="normal")
            self.aplicar_escala_hover("botao1", self.hover_escala["botao1"])
        else:
            self.canvas.itemconfigure(self.titulo_status_item, text="Áudio tocando")
            self.canvas.itemconfigure(self.exemplo_item, state="hidden")
            self.entry_tempo.place_forget()

    def restaurar_controles(self):
        self.definir_visibilidade_botao1(True)
        self.entry_tempo.config(state="normal")
        self.definir_visibilidade_botao2(True)

    def fechar_app(self):
        valor = self.entry_tempo.get().strip()
        if valor and valor not in ("inválido", "sem áudio"):
            salvar_ultimo_tempo(valor)
        self.root.destroy()

    def iniciar_contagem(self):
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
        salvar_ultimo_tempo(self.ultimo_tempo)
        self.definir_visibilidade_botao2(False)
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

        som_path = random.choice(list(audios_carregados.keys()))
        som_obj = audios_carregados[som_path]
        duracao_ms = max(1000, int(duracoes_audios[som_path] * 1000))
        self.entry_tempo.config(state="normal")
        self.entry_tempo.delete(0, tk.END)
        self.entry_tempo.insert(0, self.ultimo_tempo)
        # Os dois controles ficam fora da tela durante todo o áudio.
        self.definir_visibilidade_botao1(False)
        mostrar_popup_perfeito(duracao_ms, som_obj, self.restaurar_controles)


if __name__ == "__main__":
    root = tk.Tk()
    app = AppAlarme(root)
    # A consulta roda em segundo plano e não impede o programa de abrir.
    root.after(1500, lambda: verificar_atualizacao(root))
    root.mainloop()
