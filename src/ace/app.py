from nicegui import ui

from ace.pages import landing
from ace.pages import manager


def run():
    landing.register()
    manager.register()

    @ui.page("/coder")
    def coder_page():
        ui.label("Coder").classes("text-h4")
        ui.label("This page is under construction.")

    ui.run(host="127.0.0.1", port=8080, title="ACE", storage_secret="ace-local")
