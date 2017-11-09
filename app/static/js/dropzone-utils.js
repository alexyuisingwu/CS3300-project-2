function multiUploadDropzone(dropzoneName, successHandler, errorHandler) {
    Dropzone.options[dropzoneName] = {

        autoProcessQueue: false,
        uploadMultiple: true,
        parallelUploads: 100,
        maxFiles: 100,

        init: function() {
            var submitButton = document.getElementById('upload-csv-button')
            var courseUpload = this;

            submitButton.addEventListener("click", function(e) {
                e.preventDefault();
                e.stopPropagation();
                courseUpload.processQueue();
            });

            this.on("success", function() {
               this.options.autoProcessQueue = true;
            });

            this.on("sendingmultiple", function() {
              // Gets triggered when the form is actually being sent.
            });

            this.on("successmultiple", successHandler);

            this.on("errormultiple", errorHandler);
        }
    };
}