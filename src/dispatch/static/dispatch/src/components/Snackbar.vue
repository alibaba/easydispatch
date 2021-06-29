<template>
  <v-snackbar v-model="snackbar.show">
    {{ snackbar.text }}
    <v-btn text :color="snackbar.color" @click="closeSnackBar" :timeout="snackbar.timeout">Close</v-btn>
  </v-snackbar>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";

export default {
  name: "SnackbarInfo",
  data() {
    return {};
  },

  computed: {
    ...mapFields("app", ["snackbar"]),
  },
  methods: {
    ...mapActions("app", ["closeSnackBar"]),
  },
};
</script>
