document.addEventListener('DOMContentLoaded', function() {
    const generateBtn = document.getElementById('generateMenuBtn');
    
    if (generateBtn) {
        generateBtn.addEventListener('click', generateMenu);
    }
});

async function generateMenu() {
    try {
        const response = await fetch('/generate-weekly-menu/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            populateMenuTable(data.menu);
            showRuleCompliance(data.rule_compliance);
        } else {
            alert('Error generating menu: ' + data.error);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to generate menu');
    }
}

function populateMenuTable(menu) {
    const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'];
    
    days.forEach(day => {
        const dayMenu = menu[day];
        
        // Breakfast
        document.getElementById(`${day}Milk`).textContent = dayMenu.breakfast.milk || '';
        document.getElementById(`${day}fruit`).textContent = dayMenu.breakfast.fruit || '';
        document.getElementById(`${day}bread`).textContent = dayMenu.breakfast.bread || '';
        document.getElementById(`${day}add1`).textContent = dayMenu.breakfast.additional || '';
        
        // AM Snack
        document.getElementById(`${day}choose1`).textContent = dayMenu.am_snack.milk || '';
        document.getElementById(`${day}fruit2`).textContent = dayMenu.am_snack.fruit || '';
        document.getElementById(`${day}bread2`).textContent = dayMenu.am_snack.bread || '';
        document.getElementById(`${day}meat1`).textContent = dayMenu.am_snack.meat || '';
        
        // Lunch
        document.getElementById(`${day}Meals`).textContent = dayMenu.lunch.main_dish || '';
        document.getElementById(`${day}LunchMilk`).textContent = dayMenu.lunch.milk || '';
        document.getElementById(`${day}vege`).textContent = dayMenu.lunch.vegetable || '';
        document.getElementById(`${day}fruit3`).textContent = dayMenu.lunch.fruit || '';
        document.getElementById(`${day}Grain`).textContent = dayMenu.lunch.grain || '';
        document.getElementById(`${day}MeatAlternate`).textContent = dayMenu.lunch.meat_alternate || '';
        document.getElementById(`${day}add2`).textContent = dayMenu.lunch.additional || '';
        
        // PM Snack
        document.getElementById(`${day}choose2`).textContent = dayMenu.pm_snack.milk || '';
        document.getElementById(`${day}fruit4`).textContent = dayMenu.pm_snack.fruit || '';
        document.getElementById(`${day}bread3`).textContent = dayMenu.pm_snack.bread || '';
        document.getElementById(`${day}meat3`).textContent = dayMenu.pm_snack.meat || '';
    });
}

function showRuleCompliance(compliance) {
    // Display rule compliance status (optional visual feedback)
    console.log('Rule Compliance:', compliance);
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}