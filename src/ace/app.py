from nicegui import ui

from ace.pages import landing


def run():
    landing.register()

    @ui.page("/manager")
    def manager_page():
        ui.label("Manager").classes("text-h4")
        ui.label("This page is under construction.")

    @ui.page("/coder")
    def coder_page():
        ui.label("Coder").classes("text-h4")
        ui.label("This page is under construction.")

    ui.run(host="127.0.0.1", port=8080, title="ACE", storage_secret="ace-local")
