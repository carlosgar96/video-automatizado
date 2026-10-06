# ReflexFlow Mobile Remote

Panel móvil para controlar ReflexFlow Studio desde un navegador.

- La web se hospeda en Vercel.
- El render 1080p sigue ejecutándose en el PC con ReflexFlow Studio y FFmpeg.
- El PC debe estar encendido y la aplicación abierta.
- Los trabajos se guardan en una cola ligera usando Vercel Blob.
- El panel permite crear lotes de 1 a 10 videos y configurar duración, categoría, duración de clips y transición por video.

La API está protegida por `REFLEXFLOW_REMOTE_KEY`.
