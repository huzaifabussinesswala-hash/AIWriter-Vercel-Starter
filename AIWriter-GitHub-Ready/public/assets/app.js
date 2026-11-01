
/* =====================================================
   AIWRITER STUDIO — COMPLETE FRONTEND JAVASCRIPT
   ===================================================== */

(function () {
  'use strict';

  /* -----------------------------------------------------
     SIDEBAR COLLAPSE / RESTORE
     ----------------------------------------------------- */

  var sidebarToggle = document.getElementById('sidebar-toggle');
  var appShell = document.querySelector('.app-shell');

  if (sidebarToggle && appShell) {
    var storageKey = 'aiwriter-sidebar-collapsed';

    function readSidebarState() {
      try {
        return window.localStorage.getItem(storageKey) === 'true';
      } catch (error) {
        return false;
      }
    }

    function saveSidebarState(collapsed) {
      try {
        window.localStorage.setItem(
          storageKey,
          collapsed ? 'true' : 'false'
        );
      } catch (error) {
        // Storage may be unavailable. The toggle still works.
      }
    }

    function updateSidebarState(collapsed) {
      appShell.classList.toggle(
        'sidebar-collapsed',
        collapsed
      );

      appShell.setAttribute(
        'data-sidebar-collapsed',
        collapsed ? 'true' : 'false'
      );

      sidebarToggle.setAttribute(
        'aria-expanded',
        collapsed ? 'false' : 'true'
      );

      sidebarToggle.setAttribute(
        'aria-label',
        collapsed ? 'Show sidebar' : 'Hide sidebar'
      );

      sidebarToggle.setAttribute(
        'title',
        collapsed ? 'Show sidebar' : 'Hide sidebar'
      );

      var label = sidebarToggle.querySelector(
        '.sidebar-toggle-label'
      );

      if (label) {
        label.textContent = collapsed
          ? 'Show sidebar'
          : 'Hide sidebar';
      }
    }

    // Restore saved preference on page load.
    updateSidebarState(readSidebarState());

    // Toggle sidebar on click.
    sidebarToggle.addEventListener('click', function () {
      var currentlyCollapsed =
        appShell.classList.contains('sidebar-collapsed');

      var nextState = !currentlyCollapsed;

      updateSidebarState(nextState);
      saveSidebarState(nextState);
    });
  }

  /* -----------------------------------------------------
     MOBILE PUBLIC NAVIGATION
     ----------------------------------------------------- */

  var navToggle = document.getElementById('nav-toggle');
  var siteNav = document.getElementById('site-nav');

  if (navToggle && siteNav) {
    navToggle.addEventListener('click', function () {
      var isOpen = siteNav.classList.toggle('is-open');

      navToggle.setAttribute(
        'aria-expanded',
        isOpen ? 'true' : 'false'
      );
    });
  }

  /* -----------------------------------------------------
     FORM SUBMIT HELPERS
     ----------------------------------------------------- */

  function getSubmitButtons(form) {
    var buttons = Array.prototype.slice.call(
      form.querySelectorAll('button[type="submit"]')
    );

    if (form.id) {
      var externalButtons = document.querySelectorAll(
        'button[type="submit"][form="' + form.id + '"]'
      );

      buttons = buttons.concat(
        Array.prototype.slice.call(externalButtons)
      );
    }

    return buttons;
  }

  function setFormBusy(form, busy) {
    form.dataset.submitting = busy ? 'true' : 'false';

    if (busy) {
      form.setAttribute('aria-busy', 'true');
    } else {
      form.removeAttribute('aria-busy');
    }

    getSubmitButtons(form).forEach(function (button) {
      button.disabled = busy;
      button.classList.toggle('is-loading', busy);
    });

    var status = document.getElementById('generate-status');

    if (status && form.id === 'generate-form') {
      status.textContent = busy
        ? 'Generating your text. This can take several seconds…'
        : '';
    }
  }

  /* -----------------------------------------------------
     LOADING STATE AND DOUBLE SUBMIT PROTECTION
     ----------------------------------------------------- */

  document.querySelectorAll(
    'form[data-loading-form]'
  ).forEach(function (form) {

    form.addEventListener('submit', function (event) {
      if (form.dataset.submitting === 'true') {
        event.preventDefault();
        return;
      }

      // Allow the browser to capture form data first.
      window.setTimeout(function () {
        setFormBusy(form, true);
      }, 0);
    });

    // Reset busy state when returning through browser history.
    window.addEventListener('pageshow', function () {
      setFormBusy(form, false);
    });
  });

  /* -----------------------------------------------------
     PROMPT CHARACTER COUNTER
     ----------------------------------------------------- */

  var prompt = document.getElementById('prompt');
  var counter = document.getElementById('prompt-count');

  if (prompt && counter) {
    var max =
      counter.getAttribute('data-max') ||
      prompt.getAttribute('maxlength');

    function updatePromptCounter() {
      counter.textContent =
        prompt.value.length + ' / ' + max;
    }

    prompt.addEventListener(
      'input',
      updatePromptCounter
    );

    updatePromptCounter();
  }

  /* -----------------------------------------------------
     COPY TO CLIPBOARD
     ----------------------------------------------------- */

  function fallbackCopy(text) {
    var area = document.createElement('textarea');

    area.value = text;
    area.setAttribute('readonly', '');

    area.style.position = 'fixed';
    area.style.top = '-1000px';
    area.style.left = '-1000px';

    document.body.appendChild(area);
    area.select();

    var success = false;

    try {
      success = document.execCommand('copy');
    } catch (error) {
      success = false;
    }

    document.body.removeChild(area);

    return success;
  }

  document.querySelectorAll(
    '[data-copy-target]'
  ).forEach(function (button) {

    button.addEventListener('click', function () {
      var selector = button.getAttribute(
        'data-copy-target'
      );

      var target = document.querySelector(selector);
      var status = document.getElementById('copy-status');

      if (!target) {
        return;
      }

      var text = target.innerText;

      function finishCopy(success) {
        if (status) {
          status.textContent = success
            ? 'Copied to clipboard.'
            : 'Copy failed. Select the text and copy it manually.';
        }

        window.setTimeout(function () {
          if (status) {
            status.textContent = '';
          }
        }, 3000);
      }

      if (
        navigator.clipboard &&
        window.isSecureContext
      ) {
        navigator.clipboard.writeText(text)
          .then(function () {
            finishCopy(true);
          })
          .catch(function () {
            finishCopy(fallbackCopy(text));
          });
      } else {
        finishCopy(fallbackCopy(text));
      }
    });
  });

  /* -----------------------------------------------------
     OTP RESEND COOLDOWN
     ----------------------------------------------------- */

  var resendButton = document.getElementById('resend-btn');
  var resendNote = document.getElementById('resend-note');

  if (resendButton) {
    var remaining = parseInt(
      resendButton.getAttribute('data-cooldown') || '0',
      10
    );

    if (remaining > 0) {
      resendButton.disabled = true;

      function countdown() {
        if (remaining <= 0) {
          resendButton.disabled = false;

          if (resendNote) {
            resendNote.textContent = '';
          }

          return;
        }

        if (resendNote) {
          resendNote.textContent =
            'You can request another code in ' +
            remaining +
            ' seconds.';
        }

        remaining -= 1;

        window.setTimeout(countdown, 1000);
      }

      countdown();
    }
  }

}());
