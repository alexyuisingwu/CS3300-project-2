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

        error = false;

        console.log(changes);

        if (changes.length > 2) {
            error = true;
        } else if (changes.length === 2) {
            var change1 = changes[0].find("select");
            var change2 = changes[1].find("select");

            // 2 changes only allowed if they are swaps, and one of the original values is empty (one instructor reassigned to unassigned course)
            // otherwise, 2 changes are not allowed
            if (!(change1.val() === change2.data("original") && change2.val() === change1.data("original")
                && (change1.val() === '' || change2.val() === ''))) {
                error = true;
            }
        }
        if (error) {
            errorDiv.show();
            changes.forEach(e => {
                $(e).attr("class", "danger");
            });
            $(document).scrollTop(errorDiv.offset().top);
            return false;
        }
    });
});
