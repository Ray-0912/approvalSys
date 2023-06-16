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

function confirmAction_approve(doc_id) {
    if (confirm('是否確認要核可？')) {
        $.ajax({
            type: 'POST',
            url: '/p/approve',
            data: {
              doc_id: doc_id
            },
            success: function(response) {
              alert('執行成功！');
              location.reload();
            },
            error: function(error) {
              console.log('發生錯誤：', error);
              alert('執行失敗！');
            }
        });
    }
}

function confirmAction_delete(doc_id) {
    if (confirm('是否確認要刪除？')) {
        $.ajax({
            type: 'POST',
            url: '/p/delete',
            data: {
              doc_id: doc_id
            },
            success: function(response) {
              alert('執行成功！');
              location.reload();
            },
            error: function(error) {
              console.log('發生錯誤：', error);
              alert('執行失敗！');
            }
        });
    }
}

function confirmAction_unapprove(doc_id) {
    if (confirm('是否確認要退回？')) {
        $.ajax({
            type: 'POST',
            url: '/p/unapprove',
            data: {
              doc_id: doc_id
            },
            success: function(response) {
              alert('執行成功！');
              location.reload();
            },
            error: function(error) {
              console.log('發生錯誤：', error);
              alert('執行失敗！');
            }
        });
    }
}