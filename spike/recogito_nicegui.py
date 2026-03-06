"""
Spike: Test Recogito text-annotator v3 integration with NiceGUI.

Run with:
    python spike/recogito_nicegui.py
"""

from pathlib import Path
from nicegui import app, ui

SPIKE_DIR = Path(__file__).parent
STATIC_DIR = SPIKE_DIR / "static"

# Serve Recogito's built JS/CSS as static files
app.add_static_files("/static", str(STATIC_DIR))

SAMPLE_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "Natural language processing (NLP) is a subfield of linguistics, computer science, "
    "and artificial intelligence concerned with the interactions between computers and "
    "human language. The goal is a computer capable of understanding the contents of "
    "documents, including the contextual nuances of the language within them. "
    "Challenges in natural language processing frequently involve speech recognition, "
    "natural-language understanding, and natural-language generation."
)


@ui.page("/")
def main_page():
    ui.label("Recogito + NiceGUI Spike Test").classes("text-h4 q-mb-md")

    # ── Text container that Recogito will annotate ──
    text_container = ui.html(
        f'<div id="text-content" style="padding: 1em; border: 1px solid #ccc; '
        f'min-height: 100px; font-size: 16px; line-height: 1.6;">{SAMPLE_TEXT}</div>'
    )

    # ── Log area to show Python-received events ──
    log = ui.log(max_lines=50).classes("w-full h-64 q-mt-md")

    # ── JS→Python event handlers ──
    def on_annotation_created(e):
        log.push(f"[CREATE] {e.args}")

    def on_annotation_updated(e):
        log.push(f"[UPDATE] {e.args}")

    def on_annotation_deleted(e):
        log.push(f"[DELETE] {e.args}")

    def on_selection_changed(e):
        log.push(f"[SELECTION] {e.args}")

    ui.on("annotation_created", on_annotation_created)
    ui.on("annotation_updated", on_annotation_updated)
    ui.on("annotation_deleted", on_annotation_deleted)
    ui.on("annotation_selection", on_selection_changed)

    # ── Button: retrieve all annotations from JS ──
    async def get_annotations():
        result = await ui.run_javascript(
            "window._annotator ? window._annotator.getAnnotations() : []",
            timeout=5,
        )
        log.push(f"[GET ALL] {result}")

    ui.button("Get All Annotations", on_click=get_annotations).classes("q-mt-md")

    # ── Button: clear annotations ──
    async def clear_annotations():
        await ui.run_javascript(
            "if (window._annotator) window._annotator.clearAnnotations()",
            timeout=5,
        )
        log.push("[CLEARED] All annotations removed")

    ui.button("Clear Annotations", on_click=clear_annotations).classes("q-mt-md")

    # ── Initialise Recogito on the text container after page loads ──
    ui.add_head_html(
        '<link rel="stylesheet" href="/static/recogito/text-annotator.css">'
    )
    # Shim process.env for the UMD bundle (it references process.env.NODE_ENV)
    ui.add_head_html(
        '<script>if(typeof process==="undefined"){window.process={env:{}}}</script>'
    )
    ui.add_head_html('<script src="/static/recogito/text-annotator.umd.js"></script>')

    # Initialisation script — runs after the page has loaded
    ui.run_javascript("""
    (function initRecogito() {
        const container = document.getElementById('text-content');
        if (!container) {
            console.error('text-content container not found');
            return;
        }

        // Create the text annotator with W3C format adapter
        const anno = RecogitoJS.createTextAnnotator(container, {
            adapter: RecogitoJS.W3CTextFormat('spike-test'),
        });

        // Store globally so Python can call getAnnotations() etc.
        window._annotator = anno;

        // Wire lifecycle events → Python via emitEvent
        anno.on('createAnnotation', function(annotation) {
            emitEvent('annotation_created', annotation);
        });

        anno.on('updateAnnotation', function(annotation, previous) {
            emitEvent('annotation_updated', {updated: annotation, previous: previous});
        });

        anno.on('deleteAnnotation', function(annotation) {
            emitEvent('annotation_deleted', annotation);
        });

        anno.on('selectionChanged', function(annotations) {
            emitEvent('annotation_selection', annotations);
        });

        console.log('Recogito text-annotator initialised successfully');
    })();
    """)


ui.run(port=8080, reload=False)
