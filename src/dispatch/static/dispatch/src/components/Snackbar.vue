<template>
  <v-snackbar v-model="show" :timeout="timeout">
    {{ text }}
    <v-btn text :color="color" @click="closeSnackBar">Close</v-btn>
  </v-snackbar>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import _ from "lodash";
export default {
  name: "SnackbarInfo",
  data() {
    return {};
  },

  computed: {
    ...mapFields("app", [
      "snackbar.show",
      "snackbar.timeout",
      "snackbar.text",
      "snackbar.color",
    ]),
  },
  methods: {
    ...mapActions("app", ["closeSnackBar"]),
  },
};
</script>
