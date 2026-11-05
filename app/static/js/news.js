/* Interacciones del muro de NUEVA CANAÁN NOTICIAS (sin dependencias). */
(function () {
  "use strict";

  function setLikeState(form, button, count, data) {
    if (count) {
      count.textContent = data.total;
    }
    if (!button) {
      return;
    }
    button.classList.toggle("is-active", Boolean(data.liked));
    button.setAttribute("aria-pressed", data.liked ? "true" : "false");
    var label = button.querySelector("[data-like-label]");
    if (label) {
      label.textContent = data.liked ? "Te gusta" : "Me gusta";
    }
  }

  function bindLikeForms() {
    document.querySelectorAll("[data-like-form]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.fetch || !window.FormData) {
          return; // sin fetch el formulario sigue su curso normal
        }
        event.preventDefault();

        var button = form.querySelector("[data-like-button]");
        var postId = form.getAttribute("data-post-id");
        var count = postId
          ? document.querySelector('[data-like-count="' + postId + '"]')
          : null;

        if (button) {
          button.disabled = true;
        }

        fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "fetch" },
          credentials: "same-origin"
        })
          .then(function (response) {
            if (!response.ok) {
              throw new Error("No fue posible registrar la reacción");
            }
            return response.json();
          })
          .then(function (data) {
            setLikeState(form, button, count, data);
          })
          .catch(function () {
            // Si falla la petición asíncrona se envía el formulario completo.
            form.submit();
          })
          .finally(function () {
            if (button) {
              button.disabled = false;
            }
          });
      });
    });
  }

  function bindShareButtons() {
    document.querySelectorAll("[data-share]").forEach(function (button) {
      button.addEventListener("click", function () {
        var url = button.getAttribute("data-share-url") || window.location.href;
        var title =
          button.getAttribute("data-share-title") || document.title;

        if (navigator.share) {
          navigator.share({ title: title, url: url }).catch(function () {
            /* El usuario canceló el diálogo del sistema. */
          });
          return;
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(function () {
            var label = button.lastChild;
            var previous = label && label.nodeType === 3 ? label.textContent : "";
            if (label && label.nodeType === 3) {
              label.textContent = " Enlace copiado";
              window.setTimeout(function () {
                label.textContent = previous;
              }, 2200);
            }
          });
          return;
        }

        window.prompt("Copie el enlace de la noticia:", url);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindLikeForms();
    bindShareButtons();
  });
})();
