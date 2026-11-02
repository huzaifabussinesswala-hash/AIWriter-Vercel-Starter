
/* AIWriter Pro - Main JavaScript */
(function () {
  'use strict';

  // ==========================================
  // 1. SIDEBAR COLLAPSE / EXPAND
  // ==========================================

  var sidebarToggle = document.getElementById('sidebar-toggle');
  var appShell = document.querySelector('.app-shell');

  if (sidebarToggle && appShell) {
    var mainWrap = appShell.querySelector('.app-main-wrap');
    var desktopSidebar = window.matchMedia('(min-width: 851px)');

    // Restore saved sidebar state
    try {
      if (
        localStorage.getItem('aiwriter-sidebar-collapsed') === 'true'
      ) {
        appShell.classList.add('sidebar-collapsed');
      }
    } catch (error) {}

    // IMPORTANT: Fix desktop grid when sidebar is hidden
    function applySidebarLayout() {
      if (!mainWrap) return;

      var collapsed = appShell.classList.contains(
        'sidebar-collapsed'
      );

      if (collapsed && desktopSidebar.matches) {
        appShell.style.setProperty(
          'grid-template-columns',
          'minmax(0, 1fr)',
          'important'
        );

        mainWrap.style.setProperty(
          'grid-column',
          '1',
          'important'
        );

        mainWrap.style.setProperty('width', '100%', 'important');
        mainWrap.style.setProperty('min-width', '0', 'important');
        mainWrap.style.setProperty('max-width', '100%', 'important');

      } else {
        appShell.style.removeProperty('grid-template-columns');
        mainWrap.style.removeProperty('grid-column');
        mainWrap.style.removeProperty('width');
        mainWrap.style.removeProperty('min-width');
        mainWrap.style.removeProperty('max-width');
      }
    }

    function updateSidebarButton() {
      var collapsed = appShell.classList.contains(
        'sidebar-collapsed'
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

      applySidebarLayout();
    }

    // Apply saved state on page load
    updateSidebarButton();

    // Toggle sidebar
    sidebarToggle.addEventListener('click', function () {
      appShell.classList.toggle('sidebar-collapsed');

      try {
        localStorage.setItem(
          'aiwriter-sidebar-collapsed',
          appShell.classList.contains('sidebar-collapsed')
            ? 'true'
            : 'false'
        );
      } catch (error) {}

      updateSidebarButton();
    });

    // Handle screen resizing
    if (desktopSidebar.addEventListener) {
      desktopSidebar.addEventListener(
        'change',
        applySidebarLayout
      );
    } else if (desktopSidebar.addListener) {
      desktopSidebar.addListener(applySidebarLayout);
    }

    window.addEventListener('resize', applySidebarLayout);
  }

  // ==========================================
  // 2. MOBILE NAVIGATION
  // ==========================================

  var navToggle = document.getElementById('nav-toggle');
  var nav = document.getElementById('site-nav');

  if (navToggle && nav) {
    navToggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');

      navToggle.setAttribute(
        'aria-expanded',
        open ? 'true' : 'false'
      );
    });
  }

  // ==========================================
  // 3. FORM LOADING STATE
  // ==========================================

  function getSubmitButtons(form) {
    var buttons = Array.from(
      form.querySelectorAll('button[type="submit"]')
    );

    if (form.id) {
      var externalButtons = document.querySelectorAll(
        'button[type="submit"][form="' + form.id + '"]'
      );

      buttons = buttons.concat(Array.from(externalButtons));
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
        ? 'Generating your text. Please wait...'
        : '';
    }
  }

  document.querySelectorAll('form[data-loading-form]').forEach(
    function (form) {
      form.addEventListener('submit', function (event) {
        if (form.dataset.submitting === 'true') {
          event.preventDefault();
          return;
        }

        setFormBusy(form, true);
      });
    }
  );

  // Restore form buttons when returning to the page
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('form[data-loading-form]').forEach(
      function (form) {
        setFormBusy(form, false);
      }
    );
  });

  // ==========================================
  // 4. PROMPT CHARACTER COUNTER
  // ==========================================

  var prompt = document.getElementById('prompt');
  var counter = document.getElementById('prompt-count');

  if (prompt && counter) {
    var max =
      counter.getAttribute('data-max') ||
      prompt.getAttribute('maxlength') ||
      '';

    function updateCounter() {
      counter.textContent = prompt.value.length + ' / ' + max;
    }

    prompt.addEventListener('input', updateCounter);
    updateCounter();
  }

  // ==========================================
  // 5. COPY GENERATED CONTENT
  // ==========================================

  function fallbackCopy(text) {
    var area = document.createElement('textarea');

    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';

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

  document.querySelectorAll('[data-copy-target]').forEach(
    function (button) {
      button.addEventListener('click', function () {
        var target = document.querySelector(
          button.getAttribute('data-copy-target')
        );

        var status = document.getElementById('copy-status');

        if (!target) return;

        var text = target.innerText;

        function showResult(success) {
          if (status) {
            status.textContent = success
              ? 'Copied to clipboard!'
              : 'Copy failed. Please copy manually.';
          }

          window.setTimeout(function () {
            if (status) status.textContent = '';
          }, 3000);
        }

        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(
            function () {
              showResult(true);
            },
            function () {
              showResult(fallbackCopy(text));
            }
          );
        } else {
          showResult(fallbackCopy(text));
        }
      });
    }
  );

  // ==========================================
  // 6. RESEND OTP COOLDOWN
  // ==========================================

  var resend = document.getElementById('resend-btn');
  var resendNote = document.getElementById('resend-note');

  if (resend) {
    var remaining = parseInt(
      resend.getAttribute('data-cooldown') || '0',
      10
    );

    if (remaining > 0) {
      resend.disabled = true;

      function countdown() {
        if (remaining <= 0) {
          resend.disabled = false;

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

        remaining--;
        window.setTimeout(countdown, 1000);
      }

      countdown();
    }
  }


  // ==========================================
  // 7. QUICK-START PROMPT IDEAS
  // ==========================================

  document.querySelectorAll('[data-prompt-starter]').forEach(function (button) {
    button.addEventListener('click', function () {
      var promptField = document.getElementById('prompt');
      var typeField = document.getElementById('writing_type');
      var sample = button.getAttribute('data-prompt') || '';
      var writingType = button.getAttribute('data-writing-type') || '';

      if (!promptField) return;
      if (typeField && writingType) {
        typeField.value = writingType;
        typeField.dispatchEvent(new Event('change', { bubbles: true }));
      }
      promptField.value = sample;
      promptField.dispatchEvent(new Event('input', { bubbles: true }));
      promptField.focus();
      promptField.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  // ==========================================
  // 8. DOWNLOAD A GENERATED DRAFT
  // ==========================================

  document.querySelectorAll('[data-download-target]').forEach(function (button) {
    button.addEventListener('click', function () {
      var selector = button.getAttribute('data-download-target');
      var target = selector ? document.querySelector(selector) : null;
      var status = document.getElementById('download-status');
      if (!target) return;

      try {
        var blob = new Blob([target.innerText], { type: 'text/plain;charset=utf-8' });
        var objectUrl = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = objectUrl;
        link.download = 'aiwriter-draft.txt';
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(function () { URL.revokeObjectURL(objectUrl); }, 1000);
        if (status) status.textContent = 'Your draft download has started.';
      } catch (error) {
        if (status) status.textContent = 'Download failed. Please copy the draft instead.';
      }
    });
  });

})();