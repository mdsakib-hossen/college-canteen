// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function () {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.opacity = '0';
      alert.style.transform = 'translateX(100%)';
      alert.style.transition = 'all .4s ease';
      setTimeout(function () { alert.remove(); }, 400);
    }, 5000);
  });
});
