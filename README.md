# <img src="./Assets/Square44x44Logo.png" width="30" height="30" align="center"> UTP Calendar

![Windows](https://img.shields.io/badge/OS-Windows_10%2B-0078D6?style=flat-square&logo=windows)
![WinUI 3](https://img.shields.io/badge/UI-WinUI_3-blueviolet?style=flat-square)
![.NET 8](https://img.shields.io/badge/Framework-.NET_8-512BD4?style=flat-square&logo=dotnet)
![Python](https://img.shields.io/badge/Backend-Python-3776AB?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-Apache_2.0-green?style=flat-square)

---

## Descripción

>[!NOTE]
>Cuidamos tu privacidad. La aplicación se ejecuta localmente dentro de tu equipo; ningún dato sale de él.

UTP Calendar es una aplicación de escritorio para Windows desarrollada en **WinUI 3** con lógica en **Python**. Permite a los estudiantes de la **Universidad Tecnológica del Perú** exportar y mantener actualizados sus horarios académicos en plataformas externas (Google Calendar, Structured, Apple Calendar, Outlook, etc.) mediante un enlace de suscripción `.ics` alojado en tu nube **Nextcloud**.

Además, tienes la posibilidad de agregar múltiples calendarios de otros alumnos, personalizar las alertas de clases y mantener tu horario actualizado de forma automática al encender tu computadora (o forzar una actualización manual). Si existe un día feriado pero el profesor olvidó reprogramar la clase, el programa ignorará automáticamente las clases de ese día.

---

## Índice

- [Descripción](#-descripción)
- [Requisitos previos](#-requisitos-previos)
- [Recorrido](#-recorrido)
- [Instalación](#-instalación)
- [¿Cómo usar?](#-cómo-usar)
- [Estructura del proyecto](#-estructura-del-proyecto)
- [¿Cómo lo puedo compilar en mi equipo?](#-cómo-lo-puedo-compilar-en-mi-equipo)
- [Contribuciones](#-contribuciones)
- [Licencia](#-licencia)

---

## Requisitos previos

> [!IMPORTANT]
> Recomendamos que uses la instancia de [Nextcloud FIE](https://fie.nl.tab.digital/apps/files/files).

- **Cuenta en Nextcloud:** Necesaria para generar los enlaces de suscripción `.ics`.
- **Sistema operativo:** Windows 10 o superior.
- **Conexión a Internet:** Para acceder a Nextcloud y a los servicios necesarios.

---

## Recorrido

<table align="center">
  <tr>
    <td align="center">
      <img src="https://fie.nl.tab.digital/s/LZtyznxXEE9D3FM/download" alt="Inicio" width="2500" />
      <br>
    </td>
    <td>
      <b>Inicio:</b>
      <br><br>
      <small>Esta es la ventana principal. Desde aquí añade y administra los usuarios que desees. Automáticamente después de añadir uno, la app extraerá la foto de perfil y sus datos. También puedes actualizarlos manualmente.</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://fie.nl.tab.digital/s/2Pj68xZnG5biDGi/download" alt="Recordatorios" width="2500" />
      <br>
    </td>
    <td>
      <b>Recordatorios:</b>
      <br><br>
      <small>Desde aquí personaliza las alertas antes de cada clase. De manera predeterminada, son 120 minutos antes para la primera clase y 5 minutos antes para el resto.</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://fie.nl.tab.digital/s/iWiX3TmNFo8Z8B7/download" alt="Nextcloud" width="2500" />
      <br>
    </td>
    <td>
      <b>Nextcloud:</b>
      <br><br>
      <small>En esta ventana puedes agregar tus credenciales de Nextcloud FIE y comprobar si la conexión es exitosa.</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://fie.nl.tab.digital/s/zFHcF9PjNqBp6Cw/download" alt="Calendario" width="2500" />
      <br>
    </td>
    <td>
      <b>Calendario:</b>
      <br><br>
      <small>Revisa de forma rápida si las clases extraídas coinciden con las de tu portal, evalúa si es necesario hacer una nueva generación manual y verifica el tiempo de recordatorio por cada clase.</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://fie.nl.tab.digital/s/t5Z3r8beJ9cjccY/download" alt="Terminal" width="2500" />
      <br>
    </td>
    <td>
      <b>Terminal:</b>
      <br><br>
      <small>Supervisa el funcionamiento de los scrapers de Python en detalle y revisa cualquier error directamente desde aquí.</small>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://fie.nl.tab.digital/s/aM8tJnDkSoewoj6/download" alt="Ajustes" width="2500" />
      <br>
    </td>
    <td>
      <b>Ajustes:</b>
      <br><br>
      <small>Cambia el rango de búsqueda de los scrapers (2 meses de forma predeterminada) o usa un rango de fechas específico. Aquí también puedes actualizar la base de datos de los feriados nacionales y ajustar la consulta automática al iniciar tu computadora.</small>
    </td>
  </tr>
</table>

---

## Instalación

1. Ve a la sección [**Releases**](https://github.com/DidierEvandro/UTP-Calendar/releases).
2. Descarga la versión más reciente del instalador (`.exe`).
3. Ejecuta el instalador y sigue las instrucciones en pantalla.
4. Al finalizar, abre **UTP Calendar** desde el menú Inicio.

---

## ¿Cómo usar?

1. Abre **UTP Calendar**.
2. Haz clic en **Nuevo usuario** y agrega tu código UTP y tu contraseña. La app descargará tu foto y tus datos para que puedas diferenciarlos fácilmente si agregas varios usuarios.
3. Haz clic en **Generar .ics**, espera a que el scraper termine y revisa en la pestaña **Calendario** si tus clases coinciden con las del portal.
4. Para configurar la suscripción `.ics`, ve a la pestaña **Nextcloud** y rellena los datos solicitados.

> [!NOTE]
> **Guía:**
> - **URL del servidor:** `https://fie.nl.tab.digital`
> - **Token de aplicación:** Puedes generarla [aquí](https://fie.nl.tab.digital/settings/user/security).
> - **Carpeta de destino:** Te recomendamos crear una carpeta en la raíz de Nextcloud llamada "UTP Calendar:" `/UTP Calendar`.

5. Haz clic en **Probar conexión** y verifica que sea exitosa.
6. Vuelve a la pestaña **Usuarios** y vuelve a generar el `.ics`. Revisa las etiquetas de fecha debajo de la barra de progreso para confirmar que la subida a Nextcloud y la generación local hayan sido un éxito.
7. En la tarjeta de tu usuario de preferencia, haz clic en el ícono de enlace y agrégalo a tu app de calendario favorita.

> [!IMPORTANT]
> Asegúrate de que tu aplicación de calendario tenga soporte para calendarios de suscripción `.ics`. Además, en los ajustes de tu calendario, verifica que la opción de "eliminar alertas" esté desactivada para que puedas recibir las notificaciones de cada clase de forma correcta.
> <br>
> La frecuencia de actualización dependerá de tu app de calendario externa, por lo que es posible que, tras generar un nuevo `.ics` manualmente, los cambios no se vean reflejados inmediatamente.

**Consulta automática:**
<br><br>
Si quieres que se realice una consulta de tu horario académico en segundo plano cada vez que enciendas o reinicies tu equipo, haz lo siguiente:

8. Ve a la pestaña de **Usuarios** y asegúrate de que el usuario del cual quieres hacer la consulta en segundo plano tenga marcado el símbolo de estrella.
9. Ve a la pestaña de **Ajustes** y activa la opción **Ejecutar al iniciar la PC**. Si no se ejecuta, prueba haciendo clic en **Reparar inicio**.

---

## Estructura del proyecto

```text

📁 UTP-Calendar

📁 backend/              # Módulos Python para scraping de horarios, generación de archivos ICS e integración Nextcloud
📁 Models/               # Modelos de datos: AppSettings, CalendarEvent, UserProfile
📁 ViewModels/           # Lógica de presentación con patrón MVVM usando CommunityToolkit.Mvvm
📁 View/                 # Interfaz XAML con páginas principales de la aplicación
  └── 📁 Pages/          # Páginas individuales: CalendarPage, AdvancedPage, HelpPage, LogsPage, etc.
📁 Dialogs/              # Componentes de diálogo reutilizables: InputDialog, MessageDialog, ConfirmationDialog
📁 Services/             # Servicios de integración: ProfileStoreService, gestión de procesos Python
📁 Interop/              # Clases para interoperabilidad entre C# y Python mediante JSON
📁 Helpers/              # Convertidores y utilidades para XAML: InverseBoolConverter
📁 Converters/           # Convertidores de valores para bindings XAML
📁 Resources/            # Recursos de la aplicación: estilos, temas y configuración visual

```
---
## ¿Cómo lo puedo compilar en mi equipo?

Si deseas clonar y modificar el proyecto:

### Requisitos previos

- **Visual Studio 2022** con las siguientes cargas de trabajo:
  - Desarrollo de escritorio de .NET
  - Desarrollo de la plataforma universal de Windows
  - Componentes del Windows App SDK (WinUI 3)
- **Python 3.x** instalado y agregado al `PATH`.

### Clonar el repositorio
```bash
git clone [https://github.com/DidierEvandro/UTP-Calendar.git](https://github.com/DidierEvandro/UTP-Calendar.git)
cd UTP-Calendar
```

Abre el archivo `UTPCalendar.sln` en Visual Studio, restaura los paquetes NuGet y compila la solución.

---

## Contribuciones

> [!WARNING]
> La aplicación fue desarrollada casi enteramente mediante *vibe coding*. Si encuentras algo por mejorar, ¡tu contribución es bienvenida!

¿Encontraste un bug o tienes una mejora en mente? Puedes:

- Abrir un [**Issue**](https://github.com/DidierEvandro/UTP-Calendar/issues) para reportar errores o sugerir mejoras.
- Hacer un [**Pull Request**](https://github.com/DidierEvandro/UTP-Calendar/pulls) con tus cambios directamente.

--- 

## Licencia

Este proyecto se distribuye bajo la licencia **Apache License 2.0**.  
Puedes usarlo, modificarlo y distribuirlo libremente. Consulta el archivo [`LICENSE`](./LICENSE) para más detalles.

Desarrollado para la comunidad estudiantil de la UTP.
