<template>
  <v-card class="mx-auto" max-width="500" style="margin-top: -64px;">
    <v-card-title>
      Login to EasyDispatch
    </v-card-title>
    <v-card-text>
      <v-form>
        <v-container>
          <v-row>
            <v-col cols="12" md="12">
              <v-text-field v-model="email" label="User Name" required>
              </v-text-field>
            </v-col>
            <v-col cols="12" md="12">
              <v-text-field
                v-model="password"
                :type="'password'"
                label="Password"
                required
              ></v-text-field>
            </v-col>
          </v-row>
        </v-container>
      </v-form>
    </v-card-text>
    <v-card-actions>
      <v-list-item>
        <v-row align="center" justify="end">
          <v-btn color="primary" disabled @click="goRegister()">Register</v-btn>
          <v-spacer />
          <v-btn
            color="primary"
            @click="basicLogin({ email: email, password: password })"
            >Login</v-btn
          >
        </v-row>
      </v-list-item>
    </v-card-actions>
  </v-card>
</template>

<script>
//disabled
import { mapActions } from "vuex";

export default {
  data() {
    return {
      email: "",
      password: ""
    };
  },
  methods: {
    goRegister() {
      this.$router.push({ path: "register" });
    },
    ...mapActions("auth", ["basicLogin"])
  }
};
</script>

<style scoped></style>
