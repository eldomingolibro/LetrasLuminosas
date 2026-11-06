# 🔆 Letras Luminosas

App web **independiente** para generar **letras caja / lightbox letters** con hueco
para LED: una caja opaca hueca + una tapa translúcida que encaja a presión. Exporta
**STL** y **3MF** (2 materiales, para impresión multicolor).

Es la versión autónoma del "Letrero luminoso" del gestor `pedidos_app`, extraída
para poder desplegarla sola.

> ⚠️ **No es un sitio estático.** La malla 3D se genera en el servidor (Python:
> trimesh, shapely, matplotlib…). Por eso **no sirve Netlify Drop**; necesita un
> host que ejecute Python (Render, Railway, Fly.io, PythonAnywhere, un VPS…) o
> correrlo en local.

## Arrancar en local (Mac)
Doble clic en **`INICIAR.command`** (la primera vez crea el entorno e instala todo;
luego abre solo). O a mano:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py      # -> http://127.0.0.1:5001
```

## Estructura
```
app.py              # servidor Flask (rutas /, /preview, /generar, /vendor/<f>)
letrero_engine.py   # motor: construye caja + tapa (usa placa_engine)
placa_engine.py     # helpers de texto 3D (glifos -> polígonos)
web/
  index.html        # interfaz + visor three.js
  vendor/           # three.min.js + OrbitControls.js (offline)
requirements.txt    # dependencias Python
Procfile            # arranque gunicorn (Render/Railway/Heroku)
render.yaml         # despliegue 1-clic en Render
```

## Desplegar en Render (recomendado, tiene plan gratis)
1. Sube esta carpeta a un repo de GitHub.
2. En render.com → **New → Blueprint** y apunta al repo (usa `render.yaml`), o
   **New → Web Service** con:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`
3. Listo. La primera build tarda un poco (compila las libs 3D).

## Notas
- Las **tipografías** del selector son nombres de fuentes de macOS. En un servidor
  Linux puede que algunas no existan y matplotlib use una por defecto; el resultado
  sigue siendo válido, solo cambia el tipo de letra.
- El botón **☕ Invítame a un café** apunta a `paypal.me/eldomingolibro`.
