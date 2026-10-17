import json
import shutil
import uuid
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox
import tkinter as tk
from PIL import Image, ImageTk

try:
    from tkinterdnd2 import DND_FILES
except ImportError:
    DND_FILES = None


def registrar_area_arrastar(widget, callback):
    if DND_FILES is None or not hasattr(widget, "drop_target_register"):
        return
    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda evento: callback(evento.data))
    except Exception:
        pass


class GerenciadorTemas:
    """Armazena temas fora da instalação para sobreviver a atualizações do EXE."""

    def __init__(self, app, pasta_dados):
        self.app = app
        self.root = app.root
        self.pasta = Path(pasta_dados) / "temas"
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.indice = self.pasta / "temas.json"
        self.estado = self.pasta / "estado.json"
        self.temas = self._ler_json(self.indice, {})
        if not isinstance(self.temas, dict):
            self.temas = {}
        self.selecionado = None
        self.acao_pendente = None
        self.janela = None
        self.cards = []
        self.card_hover_atual = None
        self.hover_poll_id = None
        self._normalizar_indice()

    @staticmethod
    def _ler_json(caminho, padrao):
        try:
            with Path(caminho).open("r", encoding="utf-8") as arq:
                valor = json.load(arq)
                return valor if isinstance(valor, type(padrao)) else padrao
        except (OSError, ValueError, TypeError):
            if Path(caminho).name == "temas.json" and Path(caminho).exists():
                try:
                    backup = Path(caminho).with_name("temas.corrompido.bak")
                    if not backup.exists():
                        shutil.copy2(caminho, backup)
                except OSError:
                    pass
            return padrao

    def _salvar_json_seguro(self, caminho, dados):
        caminho = Path(caminho)
        temporario = caminho.with_suffix(caminho.suffix + ".tmp")
        with temporario.open("w", encoding="utf-8") as arq:
            json.dump(dados, arq, ensure_ascii=False, indent=2)
        temporario.replace(caminho)

    def _normalizar_indice(self):
        removidos = []
        for uid, tema in list(self.temas.items()):
            pasta = self.pasta / uid
            if not isinstance(tema, dict) or not pasta.is_dir():
                removidos.append(uid)
            elif tema.get("_id") != uid:
                tema["_id"] = uid
        for uid in removidos:
            self.temas.pop(uid, None)
        self._salvar_json_seguro(self.indice, self.temas)

    def tema_ativo(self):
        estado = self._ler_json(self.estado, {"ativo": None})
        uid = estado.get("ativo")
        if uid and uid not in self.temas:
            self._salvar_json_seguro(self.estado, {"ativo": None})
            return None
        return self.temas.get(uid) if uid else None

    def aplicar_ativo(self):
        self.app.aplicar_tema(self.tema_ativo())

    def ativar(self, uid, mostrar=True):
        if uid is None:
            self._salvar_json_seguro(self.estado, {"ativo": None})
            self.app.aplicar_tema(None)
            if mostrar and self.janela and self.janela.winfo_exists():
                messagebox.showinfo("Temas", "Tema padrão ativo.", parent=self.janela)
            return
        tema = self.temas.get(uid)
        if not tema:
            self.ativar(None, mostrar=False)
            return
        self._salvar_json_seguro(self.estado, {"ativo": uid})
        self.app.aplicar_tema(tema)
        if self.janela and self.janela.winfo_exists():
            self._atualizar_cards()
        if uid is not None:
            messagebox.showinfo("Temas", "Tema ativado com sucesso!", parent=self.janela or self.root)

    def caminho_tema(self, uid, nome):
        valor = self.temas.get(uid, {})
        relativo = valor.get(nome)
        return self.pasta / uid / relativo if relativo else None

    def abrir(self):
        if self.janela and self.janela.winfo_exists():
            self.janela.lift()
            return
        self.janela = tk.Toplevel(self.root)
        self.janela.title("Temas")
        self.janela.geometry("700x500")
        self.janela.resizable(False, False)
        self.janela.transient(self.root)
        self.janela.grab_set()
        self._centralizar(self.janela)
        self.janela.configure(bg="#35105f")
        self.janela.protocol("WM_DELETE_WINDOW", self._fechar)
        topo = tk.Frame(self.janela, bg="#35105f")
        topo.pack(fill="x", padx=18, pady=(15, 8))
        tk.Label(topo, text="Temas", bg="#35105f", fg="#fffaff",
                 font=("Trebuchet MS", 19)).pack(side="left")
        self.botao_remover = tk.Button(topo, text="Remover tema", command=lambda: self._armar_acao("remover"),
                                       width=14, relief="flat", bg="#54207e", fg="#fffaff")
        self.botao_remover.pack(side="right", padx=4)
        self.botao_editar = tk.Button(topo, text="Editar tema", command=lambda: self._armar_acao("editar"),
                                      width=14, relief="flat", bg="#7e35d2", fg="#fffaff")
        self.botao_editar.pack(side="right", padx=4)
        self.modo_label = tk.Label(self.janela, text="Selecione um tema para ativá-lo.",
                                   bg="#35105f", fg="#e3cdfb", font=("Trebuchet MS", 10))
        self.modo_label.pack(pady=(0, 2))
        self.grade = tk.Frame(self.janela, bg="#35105f")
        self.grade.pack(fill="both", expand=True, padx=18, pady=8)
        rodape = tk.Frame(self.janela, bg="#35105f")
        rodape.pack(fill="x", padx=18, pady=(0, 12))
        tk.Button(rodape, text="Fechar", command=self._fechar, width=14,
                  relief="flat", bg="#54207e", fg="#fffaff",
                  activebackground="#7737a6").pack(side="right")
        self._atualizar_cards()
        self._monitorar_hover()

    def _centralizar(self, janela):
        janela.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - janela.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - janela.winfo_height()) // 2
        janela.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _fechar(self):
        if self.hover_poll_id:
            try:
                self.janela.after_cancel(self.hover_poll_id)
            except tk.TclError:
                pass
            self.hover_poll_id = None
        try:
            self.janela.grab_release()
        except tk.TclError:
            pass
        self.janela.destroy()
        self.janela = None

    def _monitorar_hover(self):
        if not self.janela or not self.janela.winfo_exists():
            return
        try:
            x, y = self.janela.winfo_pointerx(), self.janela.winfo_pointery()
            encontrado = None
            for _uid, card in self.cards:
                if (card.winfo_rootx() <= x <= card.winfo_rootx() + card.winfo_width()
                        and card.winfo_rooty() <= y <= card.winfo_rooty() + card.winfo_height()):
                    encontrado = card
                    break
            if encontrado is not self.card_hover_atual:
                if self.card_hover_atual:
                    self._aplicar_hover(self.card_hover_atual, False)
                if encontrado:
                    self._aplicar_hover(encontrado, True)
        finally:
            self.hover_poll_id = self.janela.after(45, self._monitorar_hover)

    def _atualizar_cards(self):
        self.card_hover_atual = None
        self.grade.bind("<Motion>", self._detectar_card_hover)
        for widget in self.grade.winfo_children():
            widget.destroy()
        self.cards = []
        itens = [("padrao", {"nome": "Desemprego Joga", "logo": None})]
        itens.extend((uid, tema) for uid, tema in self.temas.items())
        while len(itens) < 6:
            itens.append((None, None))
        for indice, (uid, tema) in enumerate(itens[:6]):
            card = tk.Frame(self.grade, bg="#4a1b75", width=195, height=175,
                            highlightthickness=0)
            card.grid(row=indice // 3, column=indice % 3, padx=8, pady=8)
            card.grid_propagate(False)
            imagem = self._imagem_card(uid, tema)
            imagem_tk = ImageTk.PhotoImage(imagem)
            label_img = tk.Label(card, image=imagem_tk, bg="#4a1b75", borderwidth=0)
            label_img.image = imagem_tk
            card._imagem_base = imagem
            card._imagem_label = label_img
            label_img.pack(pady=(8, 3))
            nome = (tema or {}).get("nome", "Novo tema") if uid else ("Novo tema" if tema is None else tema["nome"])
            texto = tk.Label(card, text=nome, bg="#4a1b75", fg="#fffaff",
                             font=("Trebuchet MS", 10))
            texto.pack()
            for widget in (card, label_img, texto):
                widget.bind("<Button-1>", lambda _e, valor=uid: self._selecionar(valor))
                widget.bind("<Motion>", self._detectar_card_hover, add="+")
            card._uid = uid
            self.cards.append((uid, card))

    def _imagem_card(self, uid, tema):
        if uid == "padrao":
            caminho = self.app.CAMINHO_IMAGEM_POPUP
        elif tema and tema.get("popup"):
            caminho = self.pasta / uid / tema["popup"]
        else:
            caminho = self.app.CAMINHO_NOTHEME
        try:
            imagem = Image.open(caminho).convert("RGBA")
            imagem.thumbnail((160, 115), Image.Resampling.LANCZOS)
        except Exception:
            imagem = Image.new("RGBA", (160, 115), "#6a2ca3")
        return imagem

    def _selecionar(self, uid):
        self.selecionado = uid
        if self.acao_pendente:
            acao = self.acao_pendente
            self.acao_pendente = None
            self._atualizar_modo()
            if uid is None:
                messagebox.showinfo("Temas", "Esse espaço ainda está vazio.", parent=self.janela)
            elif uid == "padrao":
                messagebox.showinfo("Temas", "Essa ação não está disponível para o tema padrão.", parent=self.janela)
            elif acao == "editar":
                self._abrir_editor(uid)
            else:
                self._remover_uid(uid)
        elif uid is None:
            self._abrir_editor(None)
        elif uid == "padrao":
            self.ativar(None)
        else:
            self.ativar(uid)

    def _armar_acao(self, acao):
        if self.acao_pendente == acao:
            self._cancelar_acao()
            return
        self.acao_pendente = acao
        self._atualizar_modo()

    def _cancelar_acao(self):
        self.acao_pendente = None
        self._atualizar_modo()

    def _atualizar_modo(self):
        self.botao_editar.config(text="Editar tema", command=lambda: self._armar_acao("editar"),
                                 bg="#7e35d2")
        self.botao_remover.config(text="Remover tema", command=lambda: self._armar_acao("remover"),
                                  bg="#54207e")
        if self.acao_pendente == "editar":
            self.botao_editar.config(text="Cancelar ação", command=self._cancelar_acao, bg="#9b54e6")
            self.modo_label.config(text="Editar tema: agora clique no tema desejado.", fg="#f0c8ff")
        elif self.acao_pendente == "remover":
            self.botao_remover.config(text="Cancelar ação", command=self._cancelar_acao, bg="#9b6b32")
            self.modo_label.config(text="Remover tema: agora clique no tema desejado.", fg="#ffd789")
        else:
            self.modo_label.config(text="Selecione um tema para ativá-lo.", fg="#e3cdfb")

    def _remover_uid(self, uid):
        if not uid or uid == "padrao":
            messagebox.showinfo("Temas", "Selecione um tema personalizado para remover.", parent=self.janela)
            return
        if not messagebox.askyesno("Remover tema", "Deseja remover este tema?", parent=self.janela):
            return
        ativo = self._ler_json(self.estado, {"ativo": None}).get("ativo") == uid
        shutil.rmtree(self.pasta / uid, ignore_errors=True)
        self.temas.pop(uid, None)
        self._salvar_json_seguro(self.indice, self.temas)
        self.selecionado = None
        if ativo:
            self.ativar(None, mostrar=False)
        self._atualizar_cards()
        messagebox.showinfo("Temas", "Tema removido com sucesso!", parent=self.janela)

    def _agendar_hover(self, card, ativo):
        self._aplicar_hover(card, ativo)

    def _aplicar_hover(self, card, ativo):
        if self.card_hover_atual is card and not ativo:
            self.card_hover_atual = None
        elif ativo:
            self.card_hover_atual = card
        imagem = card._imagem_base.copy()
        if ativo:
            imagem.thumbnail((180, 128), Image.Resampling.LANCZOS)
        imagem_tk = ImageTk.PhotoImage(imagem)
        card._imagem_label.configure(image=imagem_tk)
        card._imagem_label.image = imagem_tk

    def _detectar_card_hover(self, event):
        x, y = event.widget.winfo_pointerx(), event.widget.winfo_pointery()
        encontrado = None
        for _uid, card in self.cards:
            if (card.winfo_rootx() <= x <= card.winfo_rootx() + card.winfo_width()
                    and card.winfo_rooty() <= y <= card.winfo_rooty() + card.winfo_height()):
                encontrado = card
                break
        if encontrado is self.card_hover_atual:
            return
        if self.card_hover_atual:
            self._aplicar_hover(self.card_hover_atual, False)
        if encontrado:
            self._aplicar_hover(encontrado, True)

    def _abrir_editor(self, uid):
        tema = dict(self.temas.get(uid, {})) if uid else {"nome": "", "cor": ""}
        editor = EditorTema(self, uid, tema)
        editor.abrir()

    def salvar_tema(self, uid, dados, arquivos):
        uid = uid or uuid.uuid4().hex
        pasta = self.pasta / uid
        temporaria = self.pasta / f".{uid}.tmp"
        registros = {"_id": uid, "nome": dados["nome"], "cor": dados.get("cor", "")}
        antigo = self.temas.get(uid, {})
        backup = self.pasta / f".{uid}.backup"
        try:
            shutil.rmtree(temporaria, ignore_errors=True)
            temporaria.mkdir(parents=True, exist_ok=True)

            for chave, origem in arquivos.items():
                origem = Path(origem) if origem else None
                if origem and origem.exists():
                    destino = temporaria / origem.name
                    shutil.copy2(origem, destino)
                    registros[chave] = destino.name
            for chave in ("logo", "background", "popup"):
                if chave not in registros and antigo.get(chave):
                    origem = pasta / antigo[chave]
                    if origem.exists():
                        shutil.copy2(origem, temporaria / origem.name)
                        registros[chave] = origem.name
            # Tema sem logo/pop-up usa o placeholder, nunca os recursos originais.
            for chave in ("logo", "popup"):
                if chave not in registros and self.g.app.CAMINHO_NOTHEME.exists():
                    destino = temporaria / "notheme.png"
                    if not destino.exists():
                        shutil.copy2(self.g.app.CAMINHO_NOTHEME, destino)
                    registros[chave] = destino.name

            registros["audios"] = []
            for origem in dados.get("audios", []):
                origem = Path(origem)
                if origem.exists():
                    destino = temporaria / origem.name
                    shutil.copy2(origem, destino)
                    registros["audios"].append(destino.name)
            if not registros["audios"] and antigo.get("audios"):
                for nome_audio in antigo["audios"]:
                    origem = pasta / nome_audio
                    if origem.exists():
                        shutil.copy2(origem, temporaria / origem.name)
                        registros["audios"].append(origem.name)

            shutil.rmtree(backup, ignore_errors=True)
            if pasta.exists():
                pasta.rename(backup)
            temporaria.rename(pasta)
            anterior = dict(self.temas)
            self.temas[uid] = registros
            try:
                self._salvar_json_seguro(self.indice, self.temas)
            except Exception:
                self.temas = anterior
                shutil.rmtree(pasta, ignore_errors=True)
                if backup.exists():
                    backup.rename(pasta)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        except Exception:
            shutil.rmtree(temporaria, ignore_errors=True)
            raise
        self.selecionado = uid
        self._atualizar_cards()
        self.ativar(uid)


class EditorTema:
    def __init__(self, gerenciador, uid, tema):
        self.g = gerenciador
        self.uid = uid
        self.tema = tema
        self.janela = None
        self.arquivos = {}
        self.audios = []
        if uid:
            pasta = self.g.pasta / uid
            for chave in ("popup", "logo", "background"):
                if tema.get(chave):
                    caminho = pasta / tema[chave]
                    if caminho.exists():
                        self.arquivos[chave] = str(caminho)
            self.audios = [str(pasta / nome) for nome in tema.get("audios", [])
                           if (pasta / nome).exists()]
        self.labels = {}
        self.previews = {}
        self.info_labels = {}
        self.nome_var = tk.StringVar(value=tema.get("nome", ""))
        self.cor = tema.get("cor", "")
        self.sujo = False

    def abrir(self):
        self.janela = tk.Toplevel(self.g.janela)
        self.janela.title("Editar tema" if self.uid else "Criar tema")
        self.janela.geometry("520x560")
        self.janela.resizable(False, False)
        self.janela.transient(self.g.janela)
        self.janela.grab_set()
        self.g._centralizar(self.janela)
        self.janela.configure(bg="#35105f")
        self.janela.protocol("WM_DELETE_WINDOW", self.fechar)
        titulo = "Editar tema" if self.uid else "Criar tema"
        tk.Label(self.janela, text=titulo, bg="#35105f", fg="#fffaff",
                 font=("Trebuchet MS", 19)).pack(pady=(14, 2))
        tk.Label(self.janela, text="Personalize a aparência e os áudios do seu tema.",
                 bg="#35105f", fg="#e3cdfb", font=("Trebuchet MS", 9)).pack(pady=(0, 8))
        tk.Label(self.janela, text="Nome do tema", bg="#35105f", fg="#fffaff",
                 font=("Trebuchet MS", 10)).pack(pady=(0, 3))
        nome = tk.Entry(self.janela, textvariable=self.nome_var, width=38)
        nome.pack()
        nome.bind("<KeyRelease>", lambda _e: self._marcar())
        tk.Label(self.janela, text="Imagens do tema", bg="#35105f", fg="#d4a9ff",
                 font=("Trebuchet MS", 11)).pack(anchor="w", padx=35, pady=(12, 2))
        self._botao_imagem("Ícone do pop-up", "popup", 55)
        self._botao_imagem("Logo do programa", "logo", 85)
        self._botao_imagem("Background", "background", 115)
        tk.Label(self.janela, text="Cor e áudio", bg="#35105f", fg="#d4a9ff",
                 font=("Trebuchet MS", 11)).pack(anchor="w", padx=35, pady=(10, 2))
        cor_frame = tk.Frame(self.janela, bg="#35105f")
        cor_frame.pack(fill="x", padx=35, pady=5)
        tk.Button(cor_frame, text="Escolher cor", command=self.escolher_cor, width=18,
                  relief="flat", bg="#7e35d2", fg="white", activebackground="#a25bea").pack(side="left")
        self.cor_label = tk.Label(cor_frame, text=self.cor or "Padrão", bg="#35105f", fg="#fffaff")
        self.cor_label.pack(side="left", padx=12)
        audio_frame = tk.Frame(self.janela, bg="#35105f")
        audio_frame.pack(fill="x", padx=35, pady=8)
        registrar_area_arrastar(audio_frame, self.receber_audios_arrastados)
        tk.Button(audio_frame, text="Importar áudios", command=self.escolher_audios, width=18,
                  relief="flat", bg="#7e35d2", fg="white", activebackground="#a25bea").pack(side="left", anchor="n")
        self.lista = tk.Listbox(audio_frame, height=5, width=28)
        self.lista.pack(side="left", padx=8)
        tk.Button(audio_frame, text="Remover", command=self.remover_audio,
                  relief="flat", bg="#54207e", fg="white", activebackground="#7737a6").pack(side="left", anchor="n")
        botoes = tk.Frame(self.janela, bg="#35105f")
        botoes.pack(side="bottom", pady=18)
        tk.Button(botoes, text="Salvar tema", command=self.salvar, width=15,
                  bg="#7e35d2", fg="white").pack(side="left", padx=7)
        tk.Button(botoes, text="Fechar", command=self.fechar, width=15,
                  bg="#54207e", fg="white").pack(side="left", padx=7)
        for caminho in self.audios:
            self.lista.insert(tk.END, Path(caminho).name)

    def _botao_imagem(self, texto, chave, y):
        frame = tk.Frame(self.janela, bg="#35105f")
        frame.pack(fill="x", padx=35, pady=3)
        tk.Button(frame, text=texto, command=lambda: self.escolher_imagem(chave), width=18,
                  relief="flat", bg="#7e35d2", fg="white", activebackground="#a25bea").pack(side="left")
        caminho = self.arquivos.get(chave)
        label = tk.Label(frame, text=Path(caminho).name if caminho else "Não selecionado",
                         name=f"lbl_{chave}", bg="#35105f", fg="#e3cdfb")
        label.pack(side="left", padx=10)
        self.labels[chave] = label
        registrar_area_arrastar(frame, lambda dados, valor=chave: self.receber_imagem_arrastada(valor, dados))
        if chave == "logo":
            aviso = tk.Label(frame, text="Ideal: 323 × 96 px", bg="#35105f",
                             fg="#d4a9ff", font=("Trebuchet MS", 8))
            aviso.pack(side="left", padx=(4, 0))
            self.info_labels[chave] = aviso
        if caminho:
            self._atualizar_preview(chave, caminho)

    def _atualizar_preview(self, chave, caminho):
        try:
            imagem = Image.open(caminho).convert("RGBA")
            imagem.thumbnail((70, 38), Image.Resampling.LANCZOS)
            preview = ImageTk.PhotoImage(imagem)
            self.previews[chave] = preview
            self.labels[chave].configure(image=preview, text="")
        except Exception:
            self.labels[chave].configure(text=Path(caminho).name, image="")

    def _marcar(self):
        self.sujo = True

    def escolher_imagem(self, chave):
        caminho = filedialog.askopenfilename(parent=self.janela, filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")])
        if caminho:
            self.receber_imagem(chave, caminho)

    def receber_imagem_arrastada(self, chave, dados):
        try:
            caminhos = self.janela.tk.splitlist(dados)
        except tk.TclError:
            caminhos = [dados]
        if caminhos:
            self.receber_imagem(chave, caminhos[0])

    def receber_imagem(self, chave, caminho):
        try:
            with Image.open(caminho) as imagem:
                imagem.verify()
        except Exception:
            messagebox.showwarning("Temas", "O arquivo arrastado não é uma imagem válida.", parent=self.janela)
            return
        self.arquivos[chave] = caminho
        self.labels[chave].config(text=Path(caminho).name)
        self._atualizar_preview(chave, caminho)
        self.sujo = True

    def escolher_audios(self):
        caminhos = filedialog.askopenfilenames(parent=self.janela, filetypes=[("Áudios", "*.wav *.mp3 *.ogg"), ("Todos", "*.*")])
        if caminhos:
            self.adicionar_audios(caminhos)

    def receber_audios_arrastados(self, dados):
        try:
            caminhos = self.janela.tk.splitlist(dados)
        except tk.TclError:
            caminhos = [dados]
        self.adicionar_audios(caminhos)

    def adicionar_audios(self, caminhos):
        validos = [str(caminho) for caminho in caminhos
                   if Path(caminho).suffix.lower() in (".wav", ".mp3", ".ogg")]
        self.audios.extend(path for path in validos if path not in self.audios)
        self.lista.delete(0, tk.END)
        for caminho in self.audios:
            self.lista.insert(tk.END, Path(caminho).name)
        if validos:
            self.sujo = True

    def remover_audio(self):
        selecionados = list(self.lista.curselection())
        for indice in reversed(selecionados):
            self.audios.pop(indice)
        self.lista.delete(0, tk.END)
        for caminho in self.audios:
            self.lista.insert(tk.END, Path(caminho).name)
        self.sujo = True

    def escolher_cor(self):
        cor = colorchooser.askcolor(title="Cor do tema", parent=self.janela)[1]
        if cor:
            self.cor = cor
            self.cor_label.config(text=cor)
            self.sujo = True

    def salvar(self):
        nome = self.nome_var.get().strip()
        if not nome:
            messagebox.showwarning("Temas", "Informe um nome para o tema antes de salvar.", parent=self.janela)
            return
        duplicado = any(uid != self.uid and isinstance(tema, dict)
                        and tema.get("nome", "").casefold() == nome.casefold()
                        for uid, tema in self.g.temas.items())
        if duplicado:
            messagebox.showwarning("Temas", "Já existe um tema com esse nome.", parent=self.janela)
            return
        dados = {"nome": nome, "cor": self.cor, "audios": self.audios}
        try:
            self.g.salvar_tema(self.uid, dados, self.arquivos)
        except (OSError, ValueError, TypeError) as erro:
            messagebox.showerror("Temas", "Não foi possível salvar este tema. Os dados anteriores foram preservados.",
                                 parent=self.janela)
            print(f"Erro ao salvar tema: {erro}")
            return
        self.sujo = False
        self.fechar(confirmar=False)
        messagebox.showinfo("Temas", "Tema salvo com sucesso!", parent=self.g.janela)

    def fechar(self, confirmar=True):
        if confirmar and self.sujo:
            resposta = messagebox.askyesno("Temas", "Descartar as alterações deste tema?", parent=self.janela)
            if not resposta:
                return
        try:
            self.janela.grab_release()
        except tk.TclError:
            pass
        self.janela.destroy()
        if self.g.janela and self.g.janela.winfo_exists():
            self.g.janela.grab_set()
