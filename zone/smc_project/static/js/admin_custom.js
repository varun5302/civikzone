// Custom JavaScript for Django Admin - User Management

document.addEventListener('DOMContentLoaded', function() {
    // Add profile completion percentage calculation
    function calculateProfileCompletion() {
        const requiredFields = [
            'id_username', 'id_email', 'id_first_name', 'id_last_name',
            'id_phone_number', 'id_aadhar_number', 'id_address', 'id_city',
            'id_state', 'id_pincode', 'id_zone', 'id_department'
        ];

        let filledFields = 0;
        requiredFields.forEach(fieldId => {
            const field = document.getElementById(fieldId);
            if (field && field.value.trim() !== '') {
                filledFields++;
            }
        });

        const percentage = Math.round((filledFields / requiredFields.length) * 100);
        const percentageField = document.getElementById('id_profile_completion_percentage');

        if (percentageField) {
            percentageField.value = percentage;
        }

        // Update progress bar if exists
        const progressBar = document.querySelector('.profile-completion-fill');
        if (progressBar) {
            progressBar.style.width = percentage + '%';
        }
    }

    // Calculate profile completion on form input
    const form = document.querySelector('.admin-custom-user form');
    if (form) {
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('input', calculateProfileCompletion);
            input.addEventListener('change', calculateProfileCompletion);
        });

        // Initial calculation
        calculateProfileCompletion();
    }

    // Add role-based field visibility
    function toggleRoleFields() {
        const roleSelect = document.getElementById('id_role');
        const zoneField = document.querySelector('.field-zone');
        const departmentField = document.querySelector('.field-department');

        if (roleSelect && zoneField && departmentField) {
            const selectedRole = roleSelect.value;

            if (selectedRole === 'administrator') {
                zoneField.style.display = 'none';
                departmentField.style.display = 'none';
            } else {
                zoneField.style.display = 'block';
                departmentField.style.display = 'block';
            }
        }
    }

    const roleSelect = document.getElementById('id_role');
    if (roleSelect) {
        roleSelect.addEventListener('change', toggleRoleFields);
        toggleRoleFields(); // Initial check
    }

    // Profile picture preview
    function updateProfilePicturePreview() {
        const fileInput = document.getElementById('id_profile_picture');
        const previewContainer = document.querySelector('.field-profile_picture_preview');

        if (fileInput && previewContainer) {
            fileInput.addEventListener('change', function(e) {
                const file = e.target.files[0];
                if (file) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        let img = previewContainer.querySelector('img');
                        if (!img) {
                            img = document.createElement('img');
                            img.style.maxWidth = '100px';
                            img.style.maxHeight = '100px';
                            previewContainer.appendChild(img);
                        }
                        img.src = e.target.result;
                    };
                    reader.readAsDataURL(file);
                }
            });
        }
    }

    updateProfilePicturePreview();

    // Add confirmation for user deletion
    const deleteButtons = document.querySelectorAll('input[name="_selected_action"][value="delete_selected"]');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const checkedBoxes = document.querySelectorAll('input[name="_selected_action"]:checked');
            if (checkedBoxes.length > 0) {
                const confirmMessage = `Are you sure you want to delete ${checkedBoxes.length} user(s)? This action cannot be undone.`;
                if (!confirm(confirmMessage)) {
                    e.preventDefault();
                }
            }
        });
    });

    // Add search functionality enhancement
    const searchInput = document.querySelector('#searchbar input[name="q"]');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.toLowerCase();
            const rows = document.querySelectorAll('#result_list tbody tr');

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(query)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }

    // Add role badges to list view
    function addRoleBadges() {
        const roleCells = document.querySelectorAll('#result_list tbody tr td:nth-child(4)'); // Assuming role is 4th column
        roleCells.forEach(cell => {
            const role = cell.textContent.trim().toLowerCase();
            cell.innerHTML = `<span class="role-${role}">${cell.textContent}</span>`;
        });
    }

    if (document.querySelector('#result_list')) {
        addRoleBadges();
    }

    // Add tooltips for better UX
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    tooltipElements.forEach(element => {
        element.setAttribute('title', element.getAttribute('data-tooltip'));
    });

    // Auto-format phone number
    const phoneInput = document.getElementById('id_phone_number');
    if (phoneInput) {
        phoneInput.addEventListener('input', function(e) {
            let value = e.target.value.replace(/\D/g, '');
            if (value.length > 10) {
                value = value.slice(0, 10);
            }
            if (value.length >= 6) {
                value = value.slice(0, 5) + '-' + value.slice(5);
            }
            e.target.value = value;
        });
    }

    // Auto-format Aadhar number
    const aadharInput = document.getElementById('id_aadhar_number');
    if (aadharInput) {
        aadharInput.addEventListener('input', function(e) {
            let value = e.target.value.replace(/\D/g, '');
            if (value.length > 12) {
                value = value.slice(0, 12);
            }
            if (value.length >= 4) {
                value = value.slice(0, 4) + '-' + value.slice(4);
            }
            if (value.length >= 8) {
                value = value.slice(0, 4) + '-' + value.slice(4, 8) + '-' + value.slice(8);
            }
            e.target.value = value;
        });
    }

    // Add form validation feedback
    const formInputs = document.querySelectorAll('.admin-custom-user input, .admin-custom-user select, .admin-custom-user textarea');
    formInputs.forEach(input => {
        input.addEventListener('blur', function() {
            if (this.required && !this.value.trim()) {
                this.style.borderColor = '#dc3545';
                this.style.boxShadow = '0 0 0 0.2rem rgba(220, 53, 69, 0.25)';
            } else {
                this.style.borderColor = '#28a745';
                this.style.boxShadow = '0 0 0 0.2rem rgba(40, 167, 69, 0.25)';
            }
        });
    });
});