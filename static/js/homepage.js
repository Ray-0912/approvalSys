function toggleContentPending(id) {
    var content = document.getElementById("content-" + id);
    content.classList.toggle('active');
    if (content.classList.contains('active')) {
        content.style.maxHeight = content.scrollHeight + 'px';
    } else {
        content.style.maxHeight = '0';
    }
}

function toggleContentCreator(id) {
    var content = document.getElementById("creator-content-" + id);
    content.classList.toggle('active');
    if (content.classList.contains('active')) {
        content.style.maxHeight = content.scrollHeight + 'px';
    } else {
        content.style.maxHeight = '0';
    }
}

function toggleContentUnapproved(id) {
    var content = document.getElementById("unapproved-content-" + id);
    content.classList.toggle('active');
    if (content.classList.contains('active')) {
        content.style.maxHeight = content.scrollHeight + 'px';
    } else {
        content.style.maxHeight = '0';
    }
}

function toggleContentAll(id) {
    var content = document.getElementById("all-content-" + id);
    content.classList.toggle('active');
    if (content.classList.contains('active')) {
        content.style.maxHeight = content.scrollHeight + 'px';
    } else {
        content.style.maxHeight = '0';
    }
}
