/* Confirmaciones y contador de fotografías del muro. */
(() => {
  "use strict";

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  const photosInput = document.querySelector("#photos");
  const fileCount = document.querySelector("#file-count");
  if (photosInput && fileCount) {
    photosInput.addEventListener("change", () => {
      const count = photosInput.files ? photosInput.files.length : 0;
      if (count === 0) {
        fileCount.textContent = "Ninguna fotografía seleccionada";
      } else if (count === 1) {
        fileCount.textContent = "1 fotografía seleccionada";
      } else {
        fileCount.textContent = `${count} fotografías seleccionadas`;
      }
    });
  }
})();
