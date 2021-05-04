<template>
  <v-dialog v-model="showDeleteDialog" persistent max-width="800px">
    <v-card>
      <v-card-title>
        <span class="headline">Delete Job?</span>
      </v-card-title>
      <!--<v-alert
        :value="alert"
        type="error"
        transition="slide-y-transition"
      >There was an issue deleting.</v-alert>-->
      <v-card-text>
        <v-container grid-list-md>
          <v-layout wrap>
            Are you sure you would like to delete this job?
          </v-layout>
        </v-container>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="blue darken-1" text @click="close">
          Cancel
        </v-btn>
        <v-btn color="red darken-1" text @click="performDelete(selectedJob)">
          Delete
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { mapState, mapActions } from "vuex";
export default {
  name: "JobDeleteDialog",
  data() {
    return {};
  },
  computed: {
    ...mapState("job", ["selectedJob", "showDeleteDialog"])
  },

  methods: {
    ...mapActions("job", ["deleteJob"]),

    performDelete(job) {
      this.$store.dispatch("job/deleteJob", job);
    },

    close() {
      this.$store.dispatch("job/showDeleteDialog", false);
    }
  }
};
</script>
