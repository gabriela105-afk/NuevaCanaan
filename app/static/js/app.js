/* Interacciones mínimas de la plataforma (JavaScript sin dependencias). */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    // Menú móvil
    var toggle = document.querySelector(".nav-toggle");
    var nav = document.getElementById("main-nav");
    if (toggle && nav) {
      toggle.addEventListener("click", function () {
        var open = nav.classList.toggle("is-open");
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }

    // Confirmación antes de acciones destructivas
    document.querySelectorAll("[data-confirm]").forEach(function (element) {
      var message = element.getAttribute("data-confirm");
      var eventName = element.tagName === "FORM" ? "submit" : "click";
      element.addEventListener(eventName, function (event) {
        if (!window.confirm(message)) {
          event.preventDefault();
        }
      });
    });

    // Contador de caracteres
    document.querySelectorAll("[data-counter]").forEach(function (field) {
      var target = document.getElementById(field.getAttribute("data-counter"));
      if (!target) return;
      var update = function () {
        target.textContent = field.value.length + " caracteres";
      };
      field.addEventListener("input", update);
      update();
    });

    // Campos condicionales (comunicados y eventos internos)
    var audienceFields = document.querySelectorAll("[data-audience-select]");
    audienceFields.forEach(function (select) {
      var form = select.closest("form") || document;
      var internalBlocks = form.querySelectorAll("[data-internal-only]");
      var update = function () {
        var isInternal = select.value === "internal";
        internalBlocks.forEach(function (block) {
          block.hidden = !isInternal;
        });
      };
      select.addEventListener("change", update);
      update();
    });
  });
})();
