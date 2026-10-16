import argparse
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox


class Atualizador:
    def __init__(self, root, args):
        self.root = root
        self.args = args
        self.root.title("Atualizando Desemprego Bot")
        self.root.geometry("390x180")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.cancelar)

        self.status = tk.StringVar(value="Preparando atualização...")
        tk.Label(root, text="Atualização disponível", font=("Trebuchet MS", 16, "normal")).pack(pady=(18, 4))
        tk.Label(root, textvariable=self.status, font=("Trebuchet MS", 10, "normal")).pack(pady=4)
        self.progresso = ttk.Progressbar(root, length=300, mode="indeterminate")
        self.progresso.pack(pady=12)
        self.progresso.start(12)
        self.root.after(150, self.executar)

    def cancelar(self):
        if messagebox.askyesno("Cancelar atualização", "Cancelar a atualização agora?"):
            self.root.destroy()

    def executar(self):
        try:
            self.status.set("Aguardando o programa fechar...")
            self.root.update_idletasks()
            self.esperar_processo()

            with tempfile.TemporaryDirectory(prefix="desemprego_update_") as pasta_temp:
                zip_path = Path(pasta_temp) / "atualizacao.zip"
                self.status.set("Baixando a atualização...")
                urllib.request.urlretrieve(self.args.url, zip_path)

                self.status.set("Extraindo arquivos...")
                pasta_extraida = Path(pasta_temp) / "extraido"
                pasta_extraida.mkdir()
                with zipfile.ZipFile(zip_path, "r") as arquivo_zip:
                    arquivo_zip.extractall(pasta_extraida)

                executavel_novo = next(pasta_extraida.rglob("Desemprego Bot.exe"), None)
                if executavel_novo is None:
                    raise RuntimeError("O ZIP não contém Desemprego Bot.exe")
                origem = executavel_novo.parent
                destino = Path(self.args.target).resolve()

                self.status.set("Instalando arquivos...")
                self.copiar_sem_atualizador(origem, destino)

            self.progresso.stop()
            self.status.set("Atualização concluída. Abrindo o programa...")
            self.root.update_idletasks()
            time.sleep(0.8)
            subprocess.Popen([str(Path(self.args.restart).resolve())], cwd=str(Path(self.args.restart).resolve().parent))
            self.root.destroy()
        except Exception as erro:
            self.progresso.stop()
            self.status.set("Não foi possível concluir a atualização.")
            messagebox.showerror(
                "Erro na atualização",
                f"A versão antiga foi mantida.\n\nDetalhes:\n{erro}",
            )
            self.root.destroy()

    def esperar_processo(self):
        """Aguarda o processo antigo encerrar, sem depender de bibliotecas externas."""
        try:
            pid = int(self.args.pid)
        except (TypeError, ValueError):
            return
        for _ in range(60):
            resultado = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if str(pid) not in resultado.stdout:
                return
            time.sleep(0.25)

    @staticmethod
    def copiar_sem_atualizador(origem, destino):
        destino.mkdir(parents=True, exist_ok=True)
        for item in origem.iterdir():
            if item.name.lower() == "atualizador.exe":
                continue
            destino_item = destino / item.name
            if item.is_dir():
                shutil.copytree(item, destino_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destino_item)


def argumentos():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--restart", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    root = tk.Tk()
    app = Atualizador(root, argumentos())
    root.mainloop()
