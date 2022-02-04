<template>
  <v-dialog v-model="showRemove" persistent max-width="800px">
    <v-card>
      <v-card-title>
        <span class="headline">Are you sure to delete your organization?</span>
      </v-card-title>
      <v-card-text>
        <v-container grid-list-md>
          <v-layout wrap>
            <span
              style="color:red"
            >You will lose all worker, job, team data in this organization and the data can not be recovered!</span>
          </v-layout>
        </v-container>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="blue darken-1" text @click="closeRemove()">Cancel</v-btn>
        <v-btn color="red darken-1" text @click="delete_org()">Delete</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { mapActions } from "vuex";
import { mapFields } from "vuex-map-fields";
export default {
  name: "OrgDeleteDialog",
  data() {
    return {};
  },
  computed: {
    ...mapFields("org", ["dialogs.showRemove"]),
  },

  methods: {
    ...mapActions("org", ["remove", "closeRemove"]),
    ...mapActions("auth", ["logout"]),
    delete_org() {
      this.remove();
      let that = this;
      setTimeout(function () {
        that.logout();
      }, 500);
    },
  },
};
</script>
