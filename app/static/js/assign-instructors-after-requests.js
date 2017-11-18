$(document).ready(function(){
    var errorDiv = $("#errors");
    var sel = $("select");
    sel.each((ind, ele) => {
        $(ele).data("original", $(ele).val())
    });


    $("#assign-instructors").submit(event => {
        var changes = [];
        sel.each((ind, ele) => {
            curr = $(ele);
            if (curr.val() !== curr.data("original")) {
                changes.push(curr.closest("tr"));
            }
        });

        if (changes.length > 1) {
            errorDiv.show();
            changes.forEach(e => {
                $(e).attr("class", "alert alert-danger");
            });
            $(document).scrollTop(errorDiv.offset().top);
            return false;
        }
    });
});
