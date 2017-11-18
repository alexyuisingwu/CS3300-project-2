

(() => {
    var selects = $('select');
    var selected;
    function refreshSelects() {
        selected = [];
        selects.each((i, obj) => {
            if (obj.value !== '') {
                selected.push(obj);
            }
        });
        var options = $('option');
        options.show();
        options.prop("disabled", false);

        for (var obj1 of selected) {
            options.each(function (i, obj2) {
                var parent = obj2.parentElement;
                if (parent.id !== obj1.id && obj1.value === obj2.value) {
                    $(this).prop("disabled", true);
                    $(this).hide();
                }
            });
        }
        selects.selectpicker('refresh');
    }

    $(document).ready(() => {
        refreshSelects();
        selects.on('change', refreshSelects);
    })
})();