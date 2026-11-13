
document.addEventListener("DOMContentLoaded", function () {

    // Botón Nueva venta
    document.querySelectorAll(".action-btn")[0]?.addEventListener("click", function () {
        alert("Módulo de ventas: próximamente podrás registrar una venta.");
    });

    // Botón Registrar gasto
    document.querySelectorAll(".action-btn")[1]?.addEventListener("click", function () {
        alert("Módulo de gastos: próximamente podrás registrar un gasto.");
    });

    // Botón Agregar producto
    document.querySelectorAll(".action-btn")[2]?.addEventListener("click", function () {
        alert("Módulo de inventario: próximamente podrás agregar productos.");
    });

    // Botón Ver informes
    document.querySelectorAll(".action-btn")[3]?.addEventListener("click", function () {
        alert("Módulo de informes: próximamente podrás consultar tus informes.");
    });

});
