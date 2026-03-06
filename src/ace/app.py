from nicegui import ui

def run():
    @ui.page("/")
    def landing():
        ui.label("ACE — Annotation Coding Environment").classes("text-h4")
        ui.label("Drop an .ace file here or create a new project")

    ui.run(host="127.0.0.1", port=8080, title="ACE")
