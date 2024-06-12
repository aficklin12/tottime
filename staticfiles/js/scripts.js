/*!
    * Start Bootstrap - SB Admin v7.0.7 (https://startbootstrap.com/template/sb-admin)
    * Copyright 2013-2023 Start Bootstrap
    * Licensed under MIT (https://github.com/StartBootstrap/startbootstrap-sb-admin/blob/master/LICENSE)
    */
    // 
// Scripts
// 

window.addEventListener('DOMContentLoaded', event => {

    // Toggle the side navigation
    const sidebarToggle = document.body.querySelector('#sidebarToggle');
    if (sidebarToggle) {
        // Uncomment Below to persist sidebar toggle between refreshes
        // if (localStorage.getItem('sb|sidebar-toggle') === 'true') {
        //     document.body.classList.toggle('sb-sidenav-toggled');
        // }
        sidebarToggle.addEventListener('click', event => {
            event.preventDefault();
            document.body.classList.toggle('sb-sidenav-toggled');
            localStorage.setItem('sb|sidebar-toggle', document.body.classList.contains('sb-sidenav-toggled'));
        });
    }

});

$(document).ready(function() {
    // Function to fetch and display out-of-stock items
    function fetchOutOfStockItems() {
        // Make an AJAX request to the out-of-stock items endpoint
        $.ajax({
            url: '/api/out-of-stock-items', // URL for out-of-stock items endpoint
            method: 'GET',
            success: function(response) {
                // Clear the existing list items
                $('#outOfStockList').empty();

                // Loop through the response data and append each item to the list
                response.forEach(function(item) {
                    $('#outOfStockList').append('<li class="list-group-item">' + item.name + '</li>');
                });
            },
            error: function(xhr, status, error) {
                // Handle errors
                console.error('Error fetching out-of-stock items:', error);
            }
        });
    }

    // Function to fetch and display items that are soon to be ordered
    function fetchOrderSoonItems() {
        // Make an AJAX request to the order-soon items endpoint
        $.ajax({
            url: '/api/order-soon-items', // URL for order-soon items endpoint
            method: 'GET',
            success: function(response) {
                // Clear the existing list items
                $('#orderSoonList').empty();

                // Loop through the response data and append each item to the list
                response.forEach(function(item) {
                    $('#orderSoonList').append('<li class="list-group-item">' + item.name + '</li>');
                });
            },
            error: function(xhr, status, error) {
                // Handle errors
                console.error('Error fetching order-soon items:', error);
            }
        });
    }

    // Call the fetchOutOfStockItems function to initially fetch and display out-of-stock items
    fetchOutOfStockItems();

    // Call the fetchOrderSoonItems function to initially fetch and display items that are soon to be ordered
    fetchOrderSoonItems();
});