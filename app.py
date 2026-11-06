"""
Letras Luminosas — app independiente (solo el Letrero luminoso).
Genera letras caja / lightbox letters con hueco para LED (caja opaca + tapa
translúcida). La malla se construye en el servidor con trimesh/shapely/matplotlib.

Arrancar en local:  python app.py   ->  http://127.0.0.1:5001
En producción (gunicorn):  gunicorn app:app
"""
import io
import os

from flask import Flask, request, jsonify, send_from_directory

import letrero_engine

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.route("/vendor/<path:filename>")
def vendor(filename):
    return send_from_directory(os.path.join(WEB, "vendor"), filename)


@app.route("/preview", methods=["POST"])
def preview():
    try:
        return jsonify(letrero_engine.build_preview(request.get_json(force=True) or {}))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/generar", methods=["POST"])
def generar():
    try:
        params = request.get_json(force=True) or {}
        if (params.get("formato") or "stl").lower() == "3mf":
            data = letrero_engine.build_scene(params).export(file_type="3mf")
            if isinstance(data, str):
                data = data.encode()
            return app.response_class(
                data, mimetype="model/3mf",
                headers={"Content-Disposition": "attachment; filename=letrero.3mf"})
        mesh = letrero_engine.build(params)
        buf = io.BytesIO()
        mesh.export(buf, file_type="stl")
        return app.response_class(
            buf.getvalue(), mimetype="model/stl",
            headers={"Content-Disposition": "attachment; filename=letrero.stl"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
