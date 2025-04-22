document.addEventListener('DOMContentLoaded', () => {
    const addTopicBtn = document.getElementById('add-topic');
    const topicInputs = document.getElementById('topic-inputs');
    const createBookBtn = document.getElementById('create-book');
    const formFeedback = document.getElementById('form-feedback');

    // Add new topic input
    addTopicBtn.addEventListener('click', () => {
        const topicGroup = document.createElement('div');
        topicGroup.className = 'mb-4 flex items-center topic-group';
        topicGroup.innerHTML = `
            <input type="text" class="topic w-full p-2 border rounded" placeholder="Enter a topic" required>
            <button type="button" class="remove-topic ml-2 bg-red-500 text-white p-2 rounded hover:bg-red-600">Remove</button>
        `;
        topicInputs.appendChild(topicGroup);
        updateRemoveButtons();
    });

    // Remove topic input
    topicInputs.addEventListener('click', (e) => {
        if (e.target.classList.contains('remove-topic')) {
            e.target.parentElement.remove();
            updateRemoveButtons();
        }
    });

    // Update visibility of remove buttons
    function updateRemoveButtons() {
        const topicGroups = document.querySelectorAll('.topic-group');
        const removeButtons = document.querySelectorAll('.remove-topic');
        removeButtons.forEach((btn, index) => {
            btn.style.display = topicGroups.length > 1 ? 'block' : 'none';
        });
    }

    // Create book
    createBookBtn.addEventListener('click', () => {
        const topics = Array.from(document.querySelectorAll('.topic')).map(input => input.value.trim()).filter(val => val);
        const bookName = document.getElementById('book-name').value.trim();
        const paperSize = document.getElementById('paper-size').value;
        const fontSize = document.getElementById('font-size').value;
        const fontStyle = document.getElementById('font-style').value;

        if (!topics.length || !bookName) {
            showFeedback('Please provide at least one topic and a book name.', 'error');
            return;
        }

        createBookBtn.disabled = true;
        createBookBtn.textContent = 'Creating...';
        formFeedback.className = 'mb-4 p-4 rounded bg-blue-100 text-blue-700';
        formFeedback.textContent = 'Generating your book...';
        formFeedback.classList.remove('hidden');

        fetch('/generate-pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topics, bookName, paperSize, fontSize, fontStyle })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showFeedback(data.error, 'error');
            } else {
                showFeedback('Book created successfully! Reloading page...', 'success');
                setTimeout(() => location.reload(), 2000);
            }
        })
        .catch(error => {
            showFeedback('An error occurred. Please try again.', 'error');
        })
        .finally(() => {
            createBookBtn.disabled = false;
            createBookBtn.textContent = 'Create Book';
        });
    });

    function showFeedback(message, type) {
        formFeedback.textContent = message;
        formFeedback.className = `mb-4 p-4 rounded ${type === 'error' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`;
        formFeedback.classList.remove('hidden');
    }
});