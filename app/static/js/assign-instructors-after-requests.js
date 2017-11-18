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

        var error = false;

        if (changes.length > 2) {
            error = true;
        } else if (changes.length === 2) {
            change1 = changes[0].find("select");
            change2 = changes[1].find("select");

            if (change1.val() !== change2.data("original") || change2.val() !== change1.data("original")) {
                error = true;
            }
        }
        if (error) {
            errorDiv.show();
            changes.forEach(e => {
                $(e).attr("class", "alert alert-danger");
            });
            $(document).scrollTop(errorDiv.offset().top);
            return false;
        }
    });
});
